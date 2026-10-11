# Argonaut Legacy

A desktop fantasy console. Games are written in **TPython**, inside the same window that runs them. There is no browser version.

Code, sprites, the map, music, and sound effects live in an `.alc` cartridge. You do not need an editor outside the console.

The editor speaks English and Russian. Press **F7**, or click the **EN / RU** chip, to switch. The choice is saved in `language.txt` next to the program. On a Russian Windows install the first launch is Russian; otherwise it is English.

---

# Argonaut Legacy

Настольная фантазийная консоль. Игру пишут на **TPython** в том же окне, где она запускается. Браузерной версии нет.

Код, спрайты, карта, музыка и эффекты живут в кассете `.alc`. Отдельный редактор снаружи не нужен.

Редактор говорит по-английски и по-русски. **F7** или метка **EN / RU** переключает язык. Выбор пишется в `language.txt` рядом с программой. На русской Windows первый запуск русский, иначе английский.

## What is inside / Что внутри

| Key / Клавиша | Editor / Редактор |
| --- | --- |
| F2 | TPython |
| F3 | Sprites, 128×128, color 0 is clear / Спрайты, цвет 0 прозрачный |
| F4 | Map, 128×32 tiles / Карта, 128×32 тайла |
| F5 | Music, pattern 32×8 / Музыка, паттерн 32×8 |
| F6 | Effects `sfx(0)` … `sfx(7)` / Эффекты |
| F7 | English or Russian / Английский или русский |
| Ctrl+R | Run / Пуск |
| Esc | Stop, back to the editor / Стоп, назад в редактор |
| F1 | Help / Справка |

In a game, arrows or WASD move, and Z and X are buttons. A is always left. D is always right.

`argonaut cart.alc` (or the portable exe with the same argument) starts that cart immediately. Esc still returns to the editor.

Sprite editor: keys **1–8** toggle the eight flags of the sprite under the cursor. **Ctrl+Z** undoes a stroke, a fill, a flag, or a palette edit. **Ctrl+Y** redoes it.

В игре стрелки или WASD ходят, Z и X — кнопки. A всегда влево, D всегда вправо.

`argonaut cart.alc` (или portable exe с тем же аргументом) сразу запускает эту кассету. Esc возвращает в редактор.

В спрайтах клавиши **1–8** переключают восемь флагов спрайта под курсором. **Ctrl+Z** отменяет штрих, заливку, флаг или правку палитры. **Ctrl+Y** повторяет.

The cart that ships with the console is Ferry of Thoth / «Паром Тота»: a boat collecting lights on a river. It is `carts/ferry.alc`.

## The machine it pretends to be / Какое железо она изображает

- **THOTH** — a 32-bit RISC at 20 MHz. Not ARM. The cycle budget is the part that is meant to be honest.
- A 60 Hz frame costs 333333 cycles. Every third frame costs 333334. The average is exactly 20 MHz. Overrun is subtracted from the next frame. If the frame does not `WFI` or `HALT` inside the budget, the **LATE** lamp lights.
- There is no pipeline, no cache, and no scanline beam. Instruction fetch is already inside the posted cost and is not charged again.
- Data access: SRAM and wave RAM add nothing. Cartridge ROM adds **1**. The framebuffer, palette, and device ports add **2**.
- **AMATERASU** — 320×240, RGB555, 511 palette slots. Slot 511 is rejected.
- The first `cls` of a frame is free, both in cycles and in the 76800-pixel write cap. After that, every pixel the blitter inspects costs **1** cycle, including a transparent sprite pixel. A fill pays its clipped area once. A fill that clips to nothing costs 0.
- **STRIBOG** — 8 channels. Music uses 0–6, effects use 7. The sample mixer stays on the host and is not sample-accurate. A pattern row costs **48** cycles and each note-on (including `OFF`) costs **8**, charged at the end of the frame before LATE. An empty cell holds the note and adds nothing.

- **THOTH** — 32-битный RISC, 20 МГц. Это не ARM. Честная часть — бюджет тактов.
- Кадр 60 Гц стоит 333333 тактов, каждый третий — 333334. В среднем ровно 20 МГц. Перерасход вычитается из следующего кадра. Если кадр не ушёл в `WFI` или `HALT` внутри бюджета, загорается **LATE**.
- Конвейера, кэша и луча развёртки нет. Выборка команды уже входит в цену инструкции и второй раз не считается.
- Данные: SRAM и волновая память без ожидания. ПЗУ кассеты — **+1**. Кадровый буфер, палитра и порты — **+2**.
- **AMATERASU** — 320×240, RGB555, 511 слотов палитры. Слот 511 отбрасывается.
- Первый `cls` кадра бесплатный и по тактам, и по потолку 76800 записей. Дальше каждый осмотренный пиксель блиттера стоит **1** такт, включая прозрачный пиксель спрайта. Заливка платит за видимый прямоугольник один раз. Заливка, которую клип срезал целиком, стоит 0.
- **STRIBOG** — 8 каналов. Музыка — 0–6, эффекты — 7. Сэмпловый микшер на стороне хоста и не потактовый. Строка паттерна стоит **48** тактов, взятие ноты (и `OFF`) — **8**. Это прибавляется в конце кадра до лампы LATE. Пустая клетка ноту держит и ничего не добавляет.

TPython compiles to THOTH assembly and runs on that machine. It is not CPython.

TPython компилируется в ассемблер THOTH и исполняется этим железом. Это не CPython.

## TPython, short / TPython коротко

Indentation, like Python. Signed 32-bit integers. Lists of numbers and strings are enough for a game. No fractions: only `//` and `%`. No classes, dicts, or floats.

Each frame the console calls `_update`, then `_draw`. Once at the start it calls `_init`.

Отступы, как в Python. Целые 32 бита со знаком. Списков чисел и строк хватает для игры. Дробей нет: только `//` и `%`. Нет классов, словарей и float.

Каждый кадр консоль зовёт `_update`, потом `_draw`. Один раз в начале — `_init`.

```python
px = 40

def _init():
    music(0)

def _update():
    global px
    if btn(1):
        px = px + 2

def _draw():
    cls(0)
    spr(1, px, 100, 2, 2)
    text("ARGONAUT", 8, 8, 1)
```

Drawing, buttons, flags, and the cycle rules are written out in [docs/tpython.md](docs/tpython.md). English first, then Russian.

Рисунок, кнопки, флаги и правила тактов расписаны в [docs/tpython.md](docs/tpython.md). Сначала английский, потом русский.

## License / Лицензия

MIT. You can fork the console, embed it, and sell a build. Games you write with it are not covered by this license: that code is yours.

MIT. Консоль можно форкать, встраивать и продавать сборку. Игры, которые вы на ней напишете, этой лицензией не связаны: их код ваш.

## Run / Запуск

From source you need Python 3.10+ and pygame.

Из исходников нужен Python 3.10+ и pygame.

```bash
pip install -r requirements.txt
python -m argonaut
python -m argonaut carts/ferry.alc
```

Windows builds that do not need Python are on the [releases](https://github.com/Nasty1028339219182/argonaut-legacy/releases) page.

- `ArgonautLegacy-*-portable.exe` is one file. Put it anywhere and run it. A `carts` folder appears beside it.
- `ArgonautLegacy-*-windows.zip` is the same console as a folder, if a single file trips an antivirus. Unzip it and run `ArgonautLegacy.exe`.

There is no installer. Copy the file or the folder to another computer and the console is there.

Готовые сборки Windows без Python лежат в [релизах](https://github.com/Nasty1028339219182/argonaut-legacy/releases).

- `ArgonautLegacy-*-portable.exe` — один файл. Кладёте куда угодно и запускаете. Рядом появится папка `carts`.
- `ArgonautLegacy-*-windows.zip` — та же консоль папкой, если одиночный файл режет антивирус. Распакуйте и запустите `ArgonautLegacy.exe`.

Установщика нет. Скопировали файл или папку на другой компьютер — консоль на месте.

Check without a window / Проверка без окна:

```bash
python -m unittest discover -s tests
python -m argonaut --selftest
```
