# Croatian Speller firmware

A Croatian-alphabet keymap for the Cyboard **Speller**, tracking the finalized
30-letter keycap set from [cyboard#74](https://github.com/Cyboard-DigitalTailor/cyboard/pull/74)
(issue [cyboard-wiki#117](https://github.com/Cyboard-DigitalTailor/cyboard-wiki/issues/117)).

This is a **ZMK_CONFIG override** — a single `speller.keymap` that replaces the
board's default English keymap at build time. Normal Spellers are untouched;
you get the Croatian layer only when you point a build at this directory.

## The layout

```
 A    B    C    Č    Ć    [Logo]
 D    DŽ   Đ    E    F    [Bluetooth]
 G    H    I    J    K    [ . ]
 L    LJ   M    N    NJ   [Backspace]
 O    P    R    S    Š    [Space]
 T    U    V    Z    Ž    [Enter]
```

All 30 letters of Gaj's Latin alphabet, including dedicated **DŽ / LJ / NJ**
digraph keys. The right-hand column keeps the Speller's special keys — Logo
(settings toggle), Bluetooth, `.`, Backspace, Space, Enter — with their normal
firmware functions. Q/W/X/Y are omitted (not in the Croatian alphabet).

## How the accented letters are produced — read this first

The firmware is **positional**: it sends the same USB/HID scancodes a real
Croatian keyboard sends, and the **host OS — set to the Croatian keyboard
layout — turns them into č ć đ š ž**. The Croatian layout (QWERTZ) places the
accented letters on the US punctuation keys:

| Cap on Speller | Scancode the board sends | Char with **Croatian** host | Char with **US** host |
|:--:|:--:|:--:|:--:|
| Č | `;`  (SEMI) | č | ; |
| Ć | `'`  (SQT)  | ć | ' |
| Đ | `]`  (RBKT) | đ | ] |
| Š | `[`  (LBKT) | š | [ |
| Ž | `\`  (BSLH) | ž | \ |
| Z | `Y`         | z | y |

QWERTZ swaps Y and Z, so the Croatian letter **Z** sends the `Y` scancode.
Every other letter (A B C D E F G H I J K L M N O P R S T U V) sits in the same
place on QWERTY and QWERTZ and maps straight through. The digraph keys are
macros that emit their two base letters (`DŽ` = `D` + `\`, `LJ` = `L`+`J`,
`NJ` = `N`+`J`); a held Shift carries to both letters (`DŽ`), unshifted gives
`dž`.

> **The customer's OS input language must be set to Croatian** for the accented
> keys to type č ć đ š ž. On a US layout those keys type `; ' ] [ \` instead.
> This is exactly how any physical Croatian keyboard behaves. One-time host
> setup is in "Testing" below.

## Building

From the flat-sibling workspace (see cyboard-wiki `decisions/0002`), with
`zmk-private` on the `speller` branch/lineage so you get the production Speller
feature set (ZMK Studio, RGB status ring, consumer "just-works" BLE pairing):

```bash
cd zmk-environment
./build.sh speller \
    --config ../zmk-keyboards/croatian-speller \
    --fw-version <version> \
    --pristine
# -> zmk-environment/out/speller-studio.uf2
```

Built against upstream ZMK instead (no `speller` branch), it still produces a
working keyboard — the settings layer just falls back to the classic
profile-select keys instead of consumer pairing.

## Testing

1. **Set the host to the Croatian layout** (one time):
   - **Windows:** Settings → Time & language → Language & region → add
     **Croatian**, or add the **Croatian** keyboard under an existing language.
     Switch to it (taskbar language button / `Win`+`Space`).
   - **macOS:** System Settings → Keyboard → Text Input → Edit… → **+** →
     Croatian → **Croatian**. Switch with the menu-bar input menu / `Ctrl`+`Space`.
   - **Linux:** `setxkbmap hr` (X11), or add the **Croatian** layout in your
     desktop's keyboard settings (Wayland).
2. **Flash:** plug the Speller in over USB-C, double-tap the reset button to
   expose the `ASSIMILATOR` drive, and drag `speller-studio.uf2` onto it. It
   reboots automatically.
3. **Type-test** in any editor. Expected output:
   - Every letter cap prints its own letter, including **č ć đ š ž** and the
     digraphs **dž lj nj** (hold Shift → uppercase).
   - **Z** prints `z` (not `y`) — the QWERTZ swap is handled.
   - `.` Backspace Space Enter behave normally.
   - If accented keys print `; ' ] [ \` instead, the host is **not** on the
     Croatian layout — fix step 1.
4. **Bluetooth:** tap the Bluetooth key to advertise, pair from the host, and
   confirm typing works wirelessly. On the production (speller-branch) build,
   holding it ~3 s clears bonds and re-enters pairing.
5. **Logo/settings + RGB:** tap the Logo key to toggle the settings layer
   (RGB controls on the bottom two rows); tap again to exit.

## Things to be aware of (firmware side)

- **Host layout dependency (by design).** Correct Croatian output requires the
  Croatian host layout, as above. If you ever want the board to type Croatian
  regardless of host layout, that means OS-specific Unicode input macros — far
  more fragile and per-OS; not recommended for a shipping unit.
- **No number keys.** The finalized 30-letter caps consumed the two right-column
  keys the English Speller used for **Caps Lock** and the **Numbers-layer
  toggle**, so this board has **no way to reach the Numbers layer and no digits**
  by default. The `Numbers` layer is still compiled in, so a user can bind a key
  to it in **ZMK Studio**; if digits should be reachable out of the box we'd need
  to spend a key on a layer toggle (or add a hold-tap/combo) — a product call.
- **Caps Lock.** Same reason — there's no Caps Lock key. Shift still works for
  capitals; the host Caps-Lock LED indicator was dropped (no key to drive it).
- **Digraph capitalization.** `DŽ`/`LJ`/`NJ` emit two base letters, so Shift
  yields the all-caps `DŽ` form, not the title-case `Dž`. This matches how
  Croatian is normally typed and is what the host expects for the digraphs.
