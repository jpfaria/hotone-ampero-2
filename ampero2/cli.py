"""ampero2: talk to the Hotone Ampero II Stage over USB (SysEx) without the editor.

Inspect
  ampero2 patches                      list the 300 patch slots (A1-1..A60-5) with names
  ampero2 show A30-3                   patch summary: model per slot, knob values (scene 1), on/off per scene, tempo, footswitches
  ampero2 dump A30-3 [out.bin]         fetch a patch, print header, optionally save the decompressed 7705-byte image
  ampero2 inventory                    firmware, CLONE captures, NAM models, user IRs on the pedal
  ampero2 templates                    the 5 user templates
  ampero2 scene                        print the active scene (1-5)
  ampero2 global N                     raw bytes of Global Settings page N (0-10)
  ampero2 eq                           Global EQ (bands, freq, Q, gain, level)
  ampero2 footswitches                 the 7 footswitch function codes of the current patch
  ampero2 listen [seconds]             print the patch the pedal broadcasts when a footswitch changes it (default 60 s)

Catalog (offline, from the editor's model table)
  ampero2 models AMP                   models of a category: index, code, "based on"
  ampero2 params AMP "Marshell 45"     knobs of a model: index, default, range
  categories: DYN FREQ WAH DRV AMP "PRE AMP" CAB IR EQ MOD DLY RVB "FX SND" "FX RTN" "FX LOOP" VOL CLONE NAM

Select / persist
  ampero2 load A30-3                   switch the pedal to that patch (no-op if already current)
  ampero2 scene 2                      select scene 1-5 of the current patch
  ampero2 save A30-3 NAME              store the edit buffer into that slot with that name (max 16 chars)
  ampero2 template-save 1 NAME         store the edit buffer as user template 1-5 (name max 11)
  ampero2 template-load 1              load user template 1-5 into the edit buffer

Edit buffer (not stored until `save`)
  ampero2 param SLOT INDEX VALUE       knob INDEX of SLOT = VALUE (float); scene 1 propagates to all scenes
  ampero2 model SLOT CAT "Model"       put a model into a slot;  model SLOT none  empties it
  ampero2 powers SCENE b0 .. b11       on/off of the 12 slots for that scene (12 values 0/1)
  ampero2 scene-name SCENE NAME        rename a scene (max 7 chars)
  ampero2 tempo BPM                    patch tempo
  ampero2 volume 0-100                 patch output volume (the value next to the speaker icon)
  ampero2 footswitches c1 .. c7        7 hex function codes (1b-1f scene 1-5, 10 bank-, 26 patch+, 0d tap, 12 tuner, 11 looper, 29 exp 1/2, ff off)
  ampero2 quick-access PARA SLOT KNOB  quick access para 1-3;  quick-access PARA off  clears it
  ampero2 exp EXP TARGET SLOT KNOB     EXP 1-3, target 1-4;  exp EXP TARGET off  clears it

Captures (uploads need the "Ampero II" editor installed: its dylib converts the files)
  ampero2 nam-upload 3 file.nam [name]     NAM Slot 1-30
  ampero2 nam-rename 3 NAME                (max 16 chars)
  ampero2 nam-delete 3
  ampero2 clone-upload 6 file.clo [name]   Sound Clone 1-30
  ampero2 clone-delete 6
  ampero2 ir-upload 2 cab.wav [name]       User IR 1-50

Global Settings (one write at a time; unknown ids or values HANG the pedal until a power cycle)
  ampero2 global-set ID VALUE [PAGE]   e.g. 0x10 1 (No Cab L = cab only), 0x04 1 8 (Bank Select = wait); ids in protocol.GLOBAL_PARAMS
  ampero2 ctrl 1 exp|single|dual       EXP/CTRL 1-2 function
  ampero2 ctrl 1 fs 29                 single-FS code (hex) of EXP/CTRL 1-2
  ampero2 eq-set "band 1" gain 3       Global EQ field: band (low cut, low shelf, band 1-4, high shelf, high cut) + enabled|freq|q|gain

Slots are 0-based: line 1 = 0..5, line 2 = 6..11 (empty slots count). Knob INDEX is 0-based, in the
order printed by `show`/`params`. Everything else (patch, scene, NAM/IR/CLONE/template slot, para,
EXP, target) is 1-based like the editor's labels.
"""
from __future__ import annotations

import sys

from .device import Ampero
from .patch import (
    GLOBAL_EQ_FIELDS,
    parse_global_eq,
    CAPTURE_NAME_FIELD,
    CAPTURE_SLOTS,
    IR_NAME_FIELD,
    IR_SLOTS,
    decode_reply,
    decompress_patch,
    firmware_version,
    name_table,
    parse_header,
    parse_image,
    patch_names,
    template_names,
)
from .catalog import Catalog
from .ir import USER_IR_BASE, ir_image, normalize_wav, samples_from_wav
from .namb import clone_image, convert_nam, upload_image
from .protocol import (
    CLONE_UPLOAD_KIND,
    IR_UPLOAD_KIND,
    msg_delete_clone,
    msg_delete_nam,
    NAM_UPLOAD_KIND,
    SCENE_REPLY_INDEX,
    frames_for_upload,
    msg_clear_slot,
    msg_query_footswitches,
    msg_query_global,
    msg_query_inventory,
    msg_set_global_eq,
    msg_clear_exp_target,
    msg_clear_quick_access,
    msg_load_template,
    msg_query_templates,
    msg_rename_nam,
    msg_save_template,
    msg_set_control_fs_code,
    msg_set_control_function,
    msg_set_exp_target,
    msg_set_patch_volume,
    msg_set_quick_access,
    is_patch_dump,
    msg_rename_scene,
    msg_set_footswitches,
    msg_set_global,
    msg_set_model,
    msg_set_tempo,
    reply_body,
    msg_get_patch,
    msg_query_scene,
    msg_load_patch,
    msg_save_patch,
    msg_scene,
    msg_scene_powers,
    msg_set_param,
    patch_index,
    patch_label,
)


def _hex(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def _slot_target(dev: Ampero, slot: int) -> tuple[int, int, int]:
    """(slot, category index, model code) of a slot in the current patch, for quick-access/EXP targets."""
    from .patch import parse_image
    img = parse_image(decompress_patch(dev.request_dump(msg_get_patch(_current_patch(dev)))))
    code = img.slot_codes[slot]
    if code is None:
        raise SystemExit(f"slot {slot} is empty")
    return slot, Catalog.load().by_code(code).category_index, code


def _current_patch(dev: Ampero) -> int:
    import struct
    return struct.unpack("<I", reply_body(dev.request(msg_query_global(9))))[0]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, args = argv[1], argv[2:]
    with Ampero() as dev:
        if cmd == "patches":
            for i, name in enumerate(patch_names(decode_reply(dev.request_dump(msg_query_inventory("patches"))))):
                print(f"{patch_label(i):7s} {name}")
        elif cmd == "show":
            img = parse_image(decompress_patch(dev.request_dump(msg_get_patch(patch_index(args[0])))))
            cat = Catalog.load()
            print(f"{patch_label(img.header.index)} {img.header.name!r}  footswitches={_hex(bytes(img.footswitches))}")
            for s, code in enumerate(img.slot_codes):
                if code is None:
                    continue
                m = cat.by_code(code)
                on = "".join("1" if p[s] else "0" for p in img.powers)
                vals = " ".join(f"{p.name}={img.param(0, s, p.index):g}" for p in m.params)
                print(f"  slot {s:2d} {m.category:7s} {m.name:20s} scenes={on}  {vals}")
            for i, (name, bpm) in enumerate(zip(img.scene_names, img.tempos)):
                print(f"  scene {i + 1} {name!r} {bpm} bpm")
        elif cmd == "inventory":
            print("firmware", firmware_version(decode_reply(dev.request_dump(msg_query_inventory("firmware")))))
            for kind in ("clones", "nams"):
                names = name_table(decode_reply(dev.request_dump(msg_query_inventory(kind))), CAPTURE_NAME_FIELD)[:CAPTURE_SLOTS]
                print(kind, {i + 1: n for i, n in enumerate(names) if n and not n.startswith("\ufffd")})
            irs = name_table(decode_reply(dev.request_dump(msg_query_inventory("irs"))), IR_NAME_FIELD)[:IR_SLOTS]
            print("irs", {i + 1: n for i, n in enumerate(irs) if n and not n.startswith("User IR")})
        elif cmd == "nam-upload":
            from pathlib import Path
            nam = Path(args[1])
            name = args[2] if len(args) > 2 else nam.stem[:16]
            img = upload_image(int(args[0]) - 1, name, convert_nam(nam))
            ack = dev.send_frames(frames_for_upload(NAM_UPLOAD_KIND, img))
            print("ack", _hex(ack.payload))
        elif cmd == "ir-upload":
            from pathlib import Path
            wav = Path(args[1])
            name = args[2] if len(args) > 2 else wav.stem[:31]
            img = ir_image(USER_IR_BASE + int(args[0]) - 1, name, samples_from_wav(normalize_wav(wav)))
            print("ack", _hex(dev.send_frames(frames_for_upload(IR_UPLOAD_KIND, img)).payload))
        elif cmd == "clone-upload":
            from pathlib import Path
            clo = Path(args[1])
            name = args[2] if len(args) > 2 else clo.stem[:16]
            print("ack", _hex(dev.send_frames(frames_for_upload(CLONE_UPLOAD_KIND, clone_image(int(args[0]) - 1, name, clo.read_bytes()))).payload))
        elif cmd == "nam-delete":
            dev.send(msg_delete_nam(int(args[0]) - 1))
        elif cmd == "clone-delete":
            dev.send(msg_delete_clone(int(args[0]) - 1))
        elif cmd == "dump":
            dump = dev.request_dump(msg_get_patch(patch_index(args[0])))
            raw = decompress_patch(dump)
            hdr = parse_header(raw)
            print(f"{patch_label(hdr.index)} {hdr.name!r} compressed={len(dump)} image={len(raw)}")
            if len(args) > 1:
                open(args[1], "wb").write(raw)
        elif cmd == "load":
            dev.send(msg_load_patch(patch_index(args[0])))
        elif cmd == "scene":
            if args:
                dev.send(msg_scene(int(args[0]) - 1))
            else:
                print(dev.request(msg_query_scene()).payload[SCENE_REPLY_INDEX] + 1)
        elif cmd == "param":
            dev.send(msg_set_param(int(args[0]), int(args[1]), float(args[2])))
        elif cmd == "powers":
            dev.send(msg_scene_powers(int(args[0]) - 1, [int(x) for x in args[1:]]))
        elif cmd == "save":
            dev.send(msg_save_patch(patch_index(args[0]), args[1]))
        elif cmd == "model":
            if args[1].lower() == "none":
                dev.send(msg_clear_slot(int(args[0])))
            else:
                m = Catalog.load().find(args[1], args[2])
                dev.send(msg_set_model(int(args[0]), m.category_index, m.code))
        elif cmd == "models":
            for m in Catalog.load().category(args[0]).models:
                print(f"{m.index:3d} 0x{m.code:08X} {m.name:24s} {m.based_on or ''}")
        elif cmd == "params":
            for p in Catalog.load().find(args[0], args[1]).params:
                print(f"{p.index:2d} {p.name:16s} default={p.default:>6s} range={p.min}..{p.max} type={p.type}")
        elif cmd == "scene-name":
            dev.send(msg_rename_scene(int(args[0]) - 1, args[1]))
        elif cmd == "tempo":
            dev.send(msg_set_tempo(int(args[0])))
        elif cmd == "global":
            print(_hex(reply_body(dev.request(msg_query_global(int(args[0]))))))
        elif cmd == "eq":
            eq = parse_global_eq(decode_reply(dev.request_dump(msg_query_global(3))))
            print(f"enabled={eq.enabled} level={eq.level:g}")
            for band, fields in eq.bands.items():
                print(f"  {band:10s} " + " ".join(f"{k}={v}" for k, v in fields.items()))
        elif cmd == "eq-set":
            dev.send(msg_set_global_eq(GLOBAL_EQ_FIELDS.index((args[0], args[1])), float(args[2])))
        elif cmd == "volume":
            dev.send(msg_set_patch_volume(int(args[0])))
        elif cmd == "quick-access":
            para = int(args[0]) - 1
            if args[1].lower() == "off":
                dev.send(msg_clear_quick_access(para))
            else:
                dev.send(msg_set_quick_access(para, *_slot_target(dev, int(args[1])), int(args[2])))
        elif cmd == "exp":
            exp, target = int(args[0]) - 1, int(args[1]) - 1
            if args[2].lower() == "off":
                dev.send(msg_clear_exp_target(exp, target))
            else:
                dev.send(msg_set_exp_target(exp, target, *_slot_target(dev, int(args[2])), int(args[3])))
        elif cmd == "templates":
            for i, name in enumerate(template_names(decode_reply(dev.request_dump(msg_query_templates())))):
                print(f"{i + 1} {name}")
        elif cmd == "template-save":
            dev.send(msg_save_template(int(args[0]), args[1]))
        elif cmd == "template-load":
            dev.send(msg_load_template(int(args[0])))
        elif cmd == "nam-rename":
            dev.send(msg_rename_nam(int(args[0]) - 1, args[1]))
        elif cmd == "ctrl":
            ctrl = int(args[0]) - 1
            if args[1] == "fs":
                dev.send(msg_set_control_fs_code(ctrl, int(args[2], 16)))
            else:
                dev.send(msg_set_control_function(ctrl, ("exp", "single", "dual").index(args[1])))
        elif cmd == "listen":
            import time
            deadline = time.monotonic() + (float(args[0]) if args else 60.0)
            chunks = []
            while time.monotonic() < deadline:
                frame = dev.receive(0.5)
                if frame is None or not is_patch_dump(frame.payload if frame.offset == 0 else chunks[0].payload if chunks else b""):
                    continue
                chunks.append(frame)
                if sum(len(c.payload) for c in chunks) >= chunks[0].length:
                    from .patch import reassemble
                    hdr = parse_header(decompress_patch(reassemble(chunks)))
                    print(f"patch {patch_label(hdr.index)} {hdr.name!r}", flush=True)
                    chunks = []
        elif cmd == "global-set":
            dev.send(msg_set_global(int(args[0], 0), int(args[1]), page=int(args[2]) if len(args) > 2 else 1))
        elif cmd == "footswitches":
            if args:
                dev.send(msg_set_footswitches([int(x, 16) for x in args]))
            else:
                print(_hex(reply_body(dev.request(msg_query_footswitches()))))
        else:
            print(__doc__)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
