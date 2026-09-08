"""ampero: talk to the Ampero II Stage over USB without the editor.

  ampero2 patches                    list the 300 patch slots with names
  ampero2 show A30-3                 patch summary: slots/models, scenes, on/off, tempo, footswitches
  ampero2 inventory                  firmware version, CLONE captures and NAM models on the pedal
  ampero2 nam-upload 3 file.nam [name]   convert (editor dylib) and upload a NAM into NAM Slot 3 (1-based)
  ampero2 ir-upload 2 cab.wav [name]     normalize (editor dylib) and upload an IR into User IR 2 (1-based)
  ampero2 clone-upload 6 file.clo [name] upload a CLONE capture into Sound Clone 6 (1-based)
  ampero2 nam-delete 3 / clone-delete 6  empty a NAM / CLONE slot (1-based)
  ampero2 dump A28-4 [out.bin]      fetch a patch, print header, optionally save decompressed image
  ampero2 load A30-3                 make the pedal switch to that patch
  ampero2 scene [2]                  print the active scene, or select scene 1-5 in the current patch
  ampero2 param 6 0 25               set slot 6, parameter 0 to 25.0 (edit buffer, not saved)
  ampero2 powers 2 0 1 0 0 1 1 1 0 0 0 0 0   on/off of the 12 slots for scene 2
  ampero2 save A28-4 PIT-TETO        store the edit buffer into that slot with that name
  ampero2 model 4 AMP "Marshell 45"  put a model into a slot (edit buffer); `model 4 none` empties it
  ampero2 models AMP                 list a category's models (index, code, based on)
  ampero2 params AMP "Marshell 45"   list a model's parameters (index, default, range)
  ampero2 scene-name 1 USBSCN        rename scene 1 (max 7 chars)
  ampero2 tempo 120                  patch tempo (bpm)
  ampero2 global 1                   read raw bytes of a Global Settings page (1..8)
  ampero2 global-set 1 0             set global param 1 (No Cab Mode L: 0 off, 1 cab only, 2 ir only)
  ampero2 footswitches [1d ff ff ff ff ff ff]   read, or write, the 7 footswitch functions (hex, ff=off)
Slots: line 1 = 0..5, line 2 = 6..11. Parameter index = knob order in the editor panel.
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
