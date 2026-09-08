# hotone-ampero-2

Controle a **Hotone Ampero II Stage** pela USB, sem o editor: protocolo SysEx
decifrado (setembro/2026, firmware V1.7.0, editor 1.x) e uma CLI/biblioteca Python.

```bash
pipx install git+https://github.com/jpfaria/hotone-ampero-2   # ou: pip install -e .
ampero2 patches                     # os 300 slots com nomes
ampero2 show A30-3                  # slots/modelos, knobs, cenas, on/off, tempo, footswitches
ampero2 load A30-3 && ampero2 scene 2 && ampero2 param 6 0 25 && ampero2 save A30-3 DET-LUGA
ampero2 model 4 AMP "Marshell 45"   # modelo num slot (catálogo do editor: ampero2 models AMP)
ampero2 nam-upload 3 captura.nam    # NAM -> slot 3 (conversor do editor via ctypes)
ampero2 ir-upload 2 cab.wav         # IR -> User IR 2
ampero2 eq                          # Global EQ
ampero2                             # lista todos os comandos
```

Sem argumentos a CLI lista tudo. `python3 -m ampero2` funciona sem instalar o script.

## O que está coberto

Patch (load, ler, gravar, listar, copiar = load + save), cena, knob, on/off por cena,
modelo no slot, nome de cena, tempo, volume, footswitches, quick access, alvo do EXP,
templates, globais (Input/Output, Bank Select, Auto Cab, display, fonte USB, EXP/CTRL,
Global Tempo, Global EQ), inventários (patches, NAM, CLONE, IR, firmware), upload/rename/
delete de NAM, upload/delete de CLONE, upload de IR. A pedaleira manda o dump do patch
novo sozinha quando você troca pelo pé. Detalhes byte a byte em [docs/protocol.md](docs/protocol.md).

## Regras que evitam travar o firmware

- Sets de globais: **um por vez**, só (página, id, valor) já documentados, ler a página depois.
  Um id ou valor errado deixa a pedaleira muda para SysEx até desligar/ligar (3 travadas
  durante a engenharia reversa).
- `save` grava o *edit buffer* no slot dado e renomeia o buffer; recarregue o patch depois.
- Uploads de NAM/IR precisam do editor "Ampero II" instalado (usa `HTUSBTools.dylib`
  por ctypes para converter `.nam` → `.namb` e normalizar o wav).

## Requisitos

macOS (CoreMIDI via `python-rtmidi`), Python ≥ 3.10, pedaleira ligada por USB
(porta `Ampero II Stage MIDI`). O editor pode ficar aberto.

## Plugin Claude Code

Este repo também é um marketplace: `claude plugin marketplace add jpfaria/hotone-ampero-2`
e habilite `ampero2@hotone-ampero-2`. A skill `ampero2` ensina o agente a usar a CLI
com as regras acima.

## Desenvolvimento

```bash
pip install -e ".[dev]" && pytest -q      # vetores capturados do editor (docs/captures)
python3 -m ampero2.catalog_build          # regenera ampero2/catalog.json do editor instalado
python3 -m ampero2.mmon_export doc.mmon   # decodifica uma captura do MIDI Monitor
```

MIT.
