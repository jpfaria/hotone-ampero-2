# Ampero II Stage por USB (SysEx) sem o editor

O editor "Ampero II" fala com a pedaleira por CoreMIDI, porta `Ampero II Stage MIDI`,
só com SysEx. Protocolo medido em 2026-09-07 espiando o editor com o MIDI Monitor
(captura completa em `docs/captures/`) e reproduzido
no pacote `ampero2` (ver README). Firmware/editor da época: app
`com.hotone.mp380`, dylib `HTUSBTools.dylib`.

## Frame

```
F0 21 25 4D 50 00 00 CK CMD LEN_lo LEN_hi OFF_lo OFF_hi  n1 n2 n3 n4 ...  F7
```

| Campo | Significado |
|---|---|
| `21 25 4D 50` | assinatura fixa ("MP") |
| `CK` | soma de todos os bytes de `LEN_hi` até antes do `F7`, mod 128 |
| `CMD` | `0x11` consulta (host→pedal), `0x12` dados (nos dois sentidos). A pedaleira sempre manda `CK`=01/03 (não confere) |
| `LEN` | tamanho do payload decodificado, 14 bits LE (7 bits por byte) |
| `OFF` | offset deste chunk no payload (dumps chegam em chunks de 185 bytes) |
| nibbles | cada byte `b` do payload vira dois bytes `b>>4`, `b&0x0F` |

Payload (decodificado): `[tipo 2B][op][alvo][len32 LE = LEN-8][LEN+5] corpo [11 00 00]`.
Floats são IEEE-754 LE. Não responde a Identity Request universal.

## Mensagens (corpo entre colchetes)

| Ação | CMD | tipo/op/alvo | corpo |
|---|---|---|---|
| selecionar cena | 12 | `01 00 00 03` | `[cena 0-4]` |
| setar parâmetro | 12 | `03 00 04 01` | `[slot 00 idx 00][float]` (edit buffer, não grava) |
| consultar cena atual | 11 | `01 00 00 03` + `00 00 00 00` (sem trailer) | resposta: byte 9 = cena |
| on/off dos blocos | 12 | `04 00 09 01` | `[cena][12 bytes 0/1, um por slot]` (bitmap inteiro da cena) |
| carregar patch | 12 | `00 00 09 00` | `[índice u32]` — sem ack se já é o patch atual |
| ler patch | 11 | `00 00 00 01` | `[índice u32]` → dump 0x12 em chunks (formato abaixo) |
| salvar edit buffer | 12 | `00 00 00 05` | `[índice u32][nome 16 chars + NUL]` |
| consulta `0A` ao clicar num bloco | 11 | `03 00 0A 01` | `[slot 00 00 00]` → float que **não** é o valor do knob (660/567 vistos); significado desconhecido |
| modelo num slot | 12 | `02 00 04 01` | `[slot 00][código u32 LE][01]`; vazio = `[slot][FF×5][01]`. **Só validado com DYN (código < 256)**; com um código de AMP (`0x0700002A`) a pedaleira parou de responder SysEx até religar — capturar o editor fazendo isso antes de usar |
| renomear cena | 12 | `07 00 09 01` | `[cena u32][nome 7 chars + NUL]` |
| tempo do patch | 12 | `02 00 09 01` | `[00 00][bpm u16 LE]` |
| ler página de Global Settings | 11 | `00 00 PG 00` + `00 00 00 00` (sem trailer) | resposta `00 00 PG 00 len32 tag dados 11 00 00`. PG: 1 Input/Output, 2 USB Audio, 3 Global EQ (94 B), 6, 7 Controls, 8 MIDI — mapeamento byte→campo só feito para PG 1 byte 15 = No Cab Mode (L) |
| setar global | 12 | `ID 00 01 00` | `[valor]` (índice da opção no dropdown). IDs da página 1: 01 Input L (0 electric, 1 acoustic, 2 line), 02 Input R, 03 Unbal Out, 04 Bal Out, 07 Unbal Source (0 normal, 1 usb only), 08 FX Send Source, 09 Bypass (0 true, 1 dsp), 0B Bal Source, 0C Power-On (0 normal, 1 mute), 10 No Cab L (0 off, 1 cab, 2 ir), 11 No Cab R. Bytes correspondentes na página 1: 0,1,3,4,8,9,6,10,11,15,16 |
| volume do patch | 12 | `01 00 09 01` | `[00 00][vol u16]` (o "100" ao lado do alto-falante) |
| quick access | 12 | `01 00 02 01` | `[para][slot][cat][código u32][param]`; vazio = `[para][FF×7]` |
| alvo do EXP | 12 | `02 00 06 01` | `[target][exp][slot][cat][código u32][param]`; vazio = `[target][exp][FF×7]` (range/curva não capturados) |
| templates de usuário | 11/12 | `04 00 00 02` lista; `02 00 00 02` `[pos+4 u32][nome 11+NUL]` salva; `03 00 00 02` `[pos+4 u32]` carrega (resposta `00 00 00 02` = imagem do template) |
| páginas `00 00 0N 00` | 11 | N=0 blob-mestre de 2640 B (firmware, [16] patch atual, [637] fonte USB, [819] modo do display…); 1 Input/Output; 2 USB Audio ([5] fonte unbal 1..3, [6..7] as outras); 3 Global EQ (148 B, floats); 6 MIDI ([0] In Source 3=Mixed, [1..3] canal TRS/BT/USB 0–15 e 16=Omni, [5] Clock Out TRS, [7] Clock Source); 7 Controls ([0]/[1] função EXP/CTRL 1/2, [2]/[3] código FS single, [4..7] dual, [8] volátil, [14] id 5 (?), [15] Global Tempo on, [16] bpm); 8 ([0] Auto Cab Match, [1] modo do display, [3] Bank Select Mode); 9 = índice do patch atual; 10 = `00 1e 78 …` |
| Global EQ | 11/12 | `00 00 03 00` lê (148 B: `[on f32]` + 30 floats na ordem low cut en/f/Q, low shelf en/f/Q/g, band1..4 en/f/Q/g, high shelf en/f/Q/g, high cut en/f/Q, depois `[level][0×3][1.0]`); `02 00 03 00` `[índice u32][float]` seta (índice = posição na lista de 30, band 1 gain = 10) |
| setar global (forma geral) | 12 | `ID 00 PG 00` | `[valor]`; página 2 id 6 = fonte USB; página 7 id 1 = `[ctrl 00 func 00]`, id 2 = `[ctrl 00 código 00]`, id 6 = Global Tempo on/off; página 8 id 1 = Auto Cab, id 2 = modo display, id 4 = Bank Select. PATCH FS FUNC e os campos da página 6 (MIDI) **sem id conhecido** |

Códigos de função de footswitch (`01 00 03 01`): Scene 1..5 = 1B..1F, Bank- 10, Patch+ 26, Tap Tempo 0D,
Tuner 12, Looper 11, EXP 1/2 29, bloco A2 0C (demais slots/Bank+/Patch- não capturados), OFF FF.

**Notificações:** ao trocar de patch pelo pé, a pedaleira manda sozinha o dump completo do patch
novo (`00 00 00 01`, mesmo formato de `ler patch`) e um `03 00 08 00 [01|00]`. O editor além disso
faz polling (`00 00 09 00` = página 9 = índice atual; `01 00 00 03` = cena).
| ler footswitches do patch | 11 | `00 00 03 01` + `00 00 00 00` | resposta: 12×FF + `10 0F 12 00` (patch sem atribuições) |
| setar footswitches | 12 | `01 00 03 01` | 7 bytes, um por footswitch: FF off, 1D = Scene 3 (outros códigos não mapeados) |

O editor faz *polling*: `00 00 01 00`/cena a cada troca e refaz `ler patch` quando a
pedaleira muda de patch (não há notificação espontânea capturada). Não capturado:
Save Template (cancelado para não sobrescrever o template 01), upload de IR/NAM,
slider de volume master, Global EQ por campo, série/paralelo (drag não gerou tráfego
num patch já em série).

Códigos de modelo vêm do catálogo do próprio editor
(`ampero2/catalog.json`, gerado por `catalog_build.py` a partir de
`App.framework/.../assets/data/v1.0.9_alg_data.json`): 609 modelos em 18 categorias,
com parâmetros (nome, índice, default, faixa, tipo). O código **não** é
`categoria<<24 | índice` (Marshell 45 é índice 43, código `0x0700002A`).

Slots: linha 1 = 0..5, linha 2 = 6..11. Índice de parâmetro = ordem dos knobs no
painel do editor (DLY Digital Delay HQ: Mix 0, Time 1, Feedback 2, Sync 3).
Índice de patch = `(banco-1)*5 + (pos-1)` (`A28-4` → 138, `A30-3` → 147).

## Dump de patch

Payload do dump = `00 00 00 01` + `len32` + fluxo **LZO1X** (raw, sem cabeçalho).
Descomprimido dá uma imagem de 7705 bytes:

| Offset | Conteúdo |
|---|---|
| 0 | índice u32 |
| 34 | nome, NUL-terminado |
| `256 + 1200·cena + 100·slot + 4·param` | float do parâmetro (5 cenas × 12 slots × 25 floats) — verificado em 3 pontos |
| ~6256 | bitmaps on/off por cena |
| 6655 | nomes das cenas ("Scene 1".."Scene 5") |

Verificado: `set_param` + `save` num slot vazio e diff contra a imagem original
mudou só índice, nome, o float esperado e um flag em 6505. Um `set_param` feito na
cena 1 apareceu nas 5 cenas; feito na cena 2 apareceu só na cena 2 (as cenas
parecem seguir a 1 até serem alteradas — não confirmado).

## Upload de NAM (`00 00 00 08`)

O editor converte o `.nam` (JSON) em `.namb` (binário, ~8 KB) com
`convertNamToNamb(char* path)` do `HTUSBTools.dylib` (chamável por ctypes; grava
`<arquivo>.namb` ao lado) e manda **uma** imagem LZO em chunks de 183 bytes:
`[soma16 do resto u32][slot u32 (0-based)][nome 20 B][01 00 00 00][namb]`.
A pedaleira responde `00 00 00 06` com `08 01 00 00 00 <slot>`. Verificado ao vivo
(`ampero2 nam-upload`): imagem idêntica à do editor, NAM aparece no inventário.
NAM: renomear = `02 00 00 08` `[slot u32][nome 16 B]`; apagar = `01 00 00 08` `[slot u32]`.

## Upload de IR (`00 00 00 04`)

O editor normaliza o wav com `getNormalWav(char* path)` do dylib (devolve o caminho de
`~/Library/Caches/HTUSBTools/HTCache/Temporary.wav`, mono 44,1 kHz 24-bit, r8brain) e manda
`[slot u32][nome 32 B][2048 × int32 (amostras 24-bit)][sum16 LE]`; "User IR n" = slot 30+n-1.
Resposta `00 00 00 06` com `04 01 00 00 00 <slot>`. Verificado ao vivo (`ampero2 ir-upload`), imagem
idêntica à do editor. Lista de IRs (`03 00 00 04`): 50 campos de 32 B; slot vazio ainda
carrega sobras "User IR n".

## Upload de CLONE (`00 00 00 07`)

Mesmo envelope do NAM: `[sum16 u32][slot u32][nome 20 B][01 00 00 00][.clo cru (cabeçalho "HTSI")]`;
ack `00 00 00 06` `07 01 00 00 00 <slot>`. Apagar = `01 00 00 07` `[slot u32]` (verificado por USB).

## Conexão (o que o editor manda ao detectar a porta)

1. `11` com payload `17 00 00 05 00 00 00 00` (sem trailer; provável "info do aparelho").
2. 5× a cada 200 ms: `F0 21 25 7F 4D 50 01 2C 11 00 00 38 00 0E 04 F7` — família de frame
   diferente (`7F` no lugar de `4D 50 00 00 CK`), sem nibbles; provável "hello/versão do editor".
3. `11` com `00 00 09 00 00 00 00 00` (patch atual), depois cena atual e `ler patch`.

Nada disso é necessário para comandar a pedaleira (as ferramentas funcionaram sem), mas é o
que o editor faz ao (re)conectar.

## Armadilhas

- **Travamento do SysEx (2× em uma sessão):** a pedaleira fica muda para todo SysEx (nem o
  handshake do editor volta) e só desligar/ligar resolve — tirar/pôr o USB não. Aconteceu (1) com
  `modelo num slot` sem o byte de categoria (corrigido) e (2) com 11 sets de Global Settings
  seguidos **feitos pelo próprio editor** (~3 s de intervalo) e (3) `01 00 06 00 [0F]` — um id
  de página 6 com valor fora da faixa (3ª travada). Regra para a tool: só mandar (página, id,
  valor) já observados no editor, um set por vez, ler a página depois (timeout = parar e avisar),
  nunca rajada, nunca sondar ids às cegas.
- Sets de globais não sobreviveram ao desliga/liga quando o firmware travou logo depois — não se
  sabe se persistem sem travamento (o No Cab Mode revertido por USB não foi testado assim).

- `save` grava o **edit buffer** no índice dado e renomeia o edit buffer; `ler patch`
  do patch atual devolve o edit buffer, não a flash. Recarregar o patch restaura.
- O editor acompanha o que a pedaleira faz (troca de patch), mas não relê knobs:
  mudanças por USB não aparecem no painel dele.
- MIDI Monitor: "copiar" trunca SysEx longos; salvar o documento (`.mmon`, plist com
  `messageData` em NSKeyedArchiver) guarda os bytes inteiros.
- Não editado ainda: trocar o modelo de um slot, renomear cena, escrever uma imagem
  inteira (o editor nunca envia a imagem; só `save` do edit buffer).
