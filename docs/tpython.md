# TPython

TPython is the language of Argonaut Legacy: a modernized TinyPython. The syntax is familiar. The semantics are narrow on purpose. If it is not described here, the language does not do it.

A cart's source compiles to THOTH assembly. A build error names the source line and leaves you in the code editor. The sentence is English or Russian, whichever language the editor is using (F7). The compiler itself stores an English key, not a finished sentence.

## Program

- Indent with spaces. One level is 4 spaces. The lexer turns tabs into spaces.
- A comment starts with `#`.
- No classes, imports, `lambda`, exceptions, `float`, `dict`, or `None` as a value.
- Numbers are signed 32-bit and wrap on overflow.
- Strings use single or double quotes. Adding strings concatenates them. Adding two numbers adds them.
- A list holds numbers only: `[1, 2, 3]`. Indexes start at 0. No slices. Negative indexes are not supported.
- `list(n)` makes a list of `n` zeros.
- `len` works on lists and strings.
- A function takes at most 6 arguments.
- `global` is required before a function writes a name declared outside it.
- `for` is only `for i in range(...)`. `range` takes one, two, or three arguments, as in Python. The step must not be zero.
- `while`, `if / elif / else`, `break`, `continue`, `pass`, `return`.
- Division is integer only: `//` and `%`. Division by zero raises a CPU fault and the frame stops.
- Comparisons produce 0 or 1. `and` / `or` / `not` are numeric too: zero is false.

Names the console calls:

| Function | When |
| --- | --- |
| `_init()` | Once, after the cart loads |
| `_update()` | Every frame, before drawing |
| `_draw()` | Every frame, after `_update` |

You can omit them. An empty cart simply stays quiet.

## Buttons

`btn(n)` stays true while the key is held. `btnp(n)` is true for one frame on the press.

| n | Key |
| --- | --- |
| 0 | left, A |
| 1 | right, D |
| 2 | up, W |
| 3 | down, S |
| 4 | Z or J |
| 5 | X or K |
| 6 | Enter |
| 7 | Tab or right Shift |

Ctrl and Alt never reach the pad. They belong to the editor.

## Drawing

The palette has 511 slots, indexes 0…510. Each RGB channel is 0…31. `pal(511, ...)` is dropped and counted in `pal_clip`.

Color 0 on a sprite is not drawn. After `cls`, zero on the screen is an ordinary background color.

| Call | Meaning |
| --- | --- |
| `cls(c)` | Clear the screen. The first clear of a frame is free |
| `pset(x, y, c)` | One pixel. Costs 1 cycle even if the clip rejects it |
| `pget(x, y)` | Pixel color, already shifted by the camera |
| `line(x0, y0, x1, y1, c)` | Line. Each plotted pixel costs 1 cycle |
| `circ(x, y, r, c)` | Circle outline |
| `circfill(x, y, r, c)` | Filled circle. Each clipped span is paid once |
| `rect(x, y, w, h, c)` | Outline |
| `rectfill(x, y, w, h, c)` | Filled rectangle. Pays the clipped area once |
| `spr(id, x, y)` | One 8×8 sprite |
| `spr(id, x, y, w, h)` | A block of tiles. `w` and `h` are in tiles |
| `map(tx, ty, x, y, w, h)` | A piece of the map. Tile 0 is empty and is not inspected |
| `text(s, x, y, c)` | A string or a number, 8×8 font. A glyph costs 64 cycles |
| `camera(x, y)` | Shift later drawing |
| `camera()` | Camera back to zero |
| `clip(x, y, w, h)` | Screen-space clip. It survives into the next frame |
| `clip()` | Clip back to 0, 0, 320, 240 |
| `pal(i, r, g, b)` | Rewrite a palette slot |

The sprite sheet is 128×128, 16 tiles per row. Sprite `n` sits in cell `(n % 16, n // 16)`.

A sprite pays 1 cycle per texel it looks at, then skips color 0. Transparent pixels are not free. The 76800 figure is a cap on pixel writes, separate from those cycles. The first `cls` of a frame does not touch either account. A later `cls` is a full-screen fill. A fill that the clip removes completely costs 0 cycles.

## Sprite flags

Each of the 256 sprites has one flag byte. The editor shows the eight bits for the sprite under the cursor (keys 1–8, or a click). `Ctrl+Z` / `Ctrl+Y` undo sprite, flag, and palette edits.

| Call | Meaning |
| --- | --- |
| `fget(id)` | The whole byte |
| `fget(id, bit)` | 0 or 1 for bit 0…7 |
| `fset(id, bit, value)` | Set the bit if `value` is not 0, otherwise clear it |

Flags live in SRAM while the cart runs. Leaving the game with Esc copies them back into the cart, so the sprite editor shows what the game wrote. They are saved with the `.alc` file. Old carts with no `flags` field load as zeros.

## Sound

| Call | Meaning |
| --- | --- |
| `music(0)` | Play the pattern from the start |
| `music(-1)` | Silence channels 0–6 |
| `sfx(n)` | Play effect slot `n` on channel 7 |

Notes in the editors are written `C4`, `D#5`, `OFF`. `OFF` silences the channel. An empty pattern cell holds the current note.

The sample mixer runs on the host. It is not timed per THOTH cycle. The sequencer is. Applying a pattern row costs 48 cycles. Each cell that starts a note or sends `OFF` costs 8 more. A hold costs nothing extra. Those cycles are added after the CPU slice and can still make the frame LATE.

Editor octave: `,` and `.`, or `-` and `=`. Notes are the row `Z X C V B N M`. Accidentals are `S D G H J`.

## Cycles

THOTH posts a cost per instruction, then adds a wait for the address of each data access:

| Region | Extra cycles |
| --- | --- |
| SRAM, wave RAM | 0 |
| Cartridge ROM, data only | +1 |
| Framebuffer, palette, PPU, APU, pad, system ports | +2 |

Instruction fetch is already inside the posted cost. It is not charged again. There is no cache and no pipeline, so a taken branch does not flush anything that was never fetched ahead.

A frame's budget is 333333 cycles, and every third frame is 333334. Finish with the runtime's wait (`WFI` happens after `_draw` if your code returns). If the budget is exceeded, or the CPU is still running, the frame is LATE and the overrun comes out of the next frame.

`cycles()` reads the cycles spent in the current frame, not including the sequencer cost that is added after the CPU stops.

## Other calls

| Call | Meaning |
| --- | --- |
| `print(v)` | A line in the console log, not on the screen |
| `frame()` | Frame number |
| `cycles()` | Cycles spent by the CPU in this frame so far |
| `rnd(n)` | An integer from 0 to n−1 |
| `abs` `min` `max` | The usual, on integers |
| `peek(addr)` `poke(addr, v)` | One SRAM byte. PPU and APU ports are not poked; they have their own calls |

`Ctrl+S` writes the cart into `carts` next to the project, or next to the exe. The name is letters, digits, `-`, and `_`. `Ctrl+P` accepts `run`, `new`, `save name`, `load name`.

`python -m argonaut carts/ferry.alc` runs that file and skips the idle editor. Esc comes back.

---

# TPython

TPython — язык Argonaut Legacy, модернизированный TinyPython. Синтаксис узнаваем. Семантика узкая намеренно. Если этого нет в описании, язык этого не умеет.

Исходник кассеты компилируется в ассемблер THOTH. Ошибка сборки называет строку и оставляет вас в редакторе кода. Фраза будет на английском или русском — на языке редактора (F7). Сам компилятор хранит английский ключ, а не готовую фразу.

## Программа

- Отступы пробелами, один уровень — 4 пробела. Табы lexer приводит к пробелам.
- Комментарий начинается с `#`.
- Нет классов, импортов, `lambda`, исключений, `float`, `dict`, `None` как значения.
- Числа — знаковые 32 бита. Переполнение заворачивается.
- Строки в двойных или одинарных кавычках. Сложение строк склеивает. Сложение двух чисел складывает.
- Список — только из чисел: `[1, 2, 3]`. Индексация с нуля, без срезов. Отрицательный индекс не поддержан.
- `list(n)` создаёт список из `n` нулей.
- `len` работает для списков и строк.
- Функция принимает не больше 6 аргументов.
- `global` обязателен, если функция пишет в имя, объявленное снаружи.
- `for` умеет только `for i in range(...)`. У `range` один, два или три аргумента, как в Python, шаг не ноль.
- `while`, `if / elif / else`, `break`, `continue`, `pass`, `return`.
- Деление только целочисленное: `//` и `%`. Деление на ноль поднимает fault процессора, и кадр останавливается.
- Сравнения дают 0 или 1. `and` / `or` / `not` тоже про числа: ноль ложен.

Имена, которые зовёт консоль:

| Функция | Когда |
| --- | --- |
| `_init()` | Один раз после загрузки кассеты |
| `_update()` | Каждый кадр, до рисования |
| `_draw()` | Каждый кадр, после `_update` |

Их можно не писать. Пустая кассета просто молчит.

## Кнопки

`btn(n)` держится, пока клавиша нажата. `btnp(n)` истинен один кадр на нажатие.

| n | Клавиша |
| --- | --- |
| 0 | влево, A |
| 1 | вправо, D |
| 2 | вверх, W |
| 3 | вниз, S |
| 4 | Z или J |
| 5 | X или K |
| 6 | Enter |
| 7 | Tab или правый Shift |

Ctrl и Alt не попадают в пад: это клавиши редактора.

## Рисунок

Палитра — 511 слотов, индексы 0…510. Каждый канал RGB от 0 до 31. `pal(511, ...)` железо выбрасывает и считает в `pal_clip`.

Цвет 0 на спрайте не рисуется. На экране после `cls` ноль — обычный цвет фона.

| Вызов | Смысл |
| --- | --- |
| `cls(c)` | Очистить экран. Первая очистка кадра бесплатна |
| `pset(x, y, c)` | Точка. 1 такт, даже если клип её отверг |
| `pget(x, y)` | Цвет точки, уже со сдвигом камеры |
| `line(x0, y0, x1, y1, c)` | Линия. Каждый поставленный пиксель стоит 1 такт |
| `circ(x, y, r, c)` | Контур окружности |
| `circfill(x, y, r, c)` | Залитый круг. Каждый видимый отрезок оплачивается один раз |
| `rect(x, y, w, h, c)` | Контур |
| `rectfill(x, y, w, h, c)` | Прямоугольник. Платит за видимую область один раз |
| `spr(id, x, y)` | Спрайт 8×8 |
| `spr(id, x, y, w, h)` | Блок тайлов, `w` и `h` в тайлах |
| `map(tx, ty, x, y, w, h)` | Кусок карты. Тайл 0 пустой и не осматривается |
| `text(s, x, y, c)` | Строка или число, шрифт 8×8. Глиф стоит 64 такта |
| `camera(x, y)` | Сдвиг последующего рисунка |
| `camera()` | Камера в ноль |
| `clip(x, y, w, h)` | Клип в координатах экрана. Живёт и в следующем кадре |
| `clip()` | Клип снова 0, 0, 320, 240 |
| `pal(i, r, g, b)` | Переписать слот палитры |

Лист спрайтов — 128×128, 16 тайлов в ряд. Спрайт `n` стоит в клетке `(n % 16, n // 16)`.

Спрайт платит 1 такт за каждый осмотренный тексель и пропускает цвет 0. Прозрачные пиксели не бесплатны. Число 76800 — потолок записей, отдельно от этих тактов. Первый `cls` кадра не трогает ни то, ни другое. Следующий `cls` — заливка всего экрана. Заливка, которую клип срезал целиком, стоит 0 тактов.

## Флаги спрайтов

У каждого из 256 спрайтов один байт флагов. Редактор показывает восемь бит спрайта под курсором (клавиши 1–8 или клик). `Ctrl+Z` / `Ctrl+Y` отменяют правки спрайта, флагов и палитры.

| Вызов | Смысл |
| --- | --- |
| `fget(id)` | Весь байт |
| `fget(id, bit)` | 0 или 1 для бита 0…7 |
| `fset(id, bit, value)` | Ставит бит, если `value` не 0, иначе снимает |

Пока кассета работает, флаги лежат в SRAM. Esc из игры копирует их обратно в кассету, и редактор спрайтов показывает то, что записала игра. Они сохраняются в файл `.alc`. Старая кассета без поля `flags` читается как нули.

## Звук

| Вызов | Смысл |
| --- | --- |
| `music(0)` | Играть паттерн с начала |
| `music(-1)` | Замолчать каналы 0–6 |
| `sfx(n)` | Проиграть слот эффекта на канале 7 |

Ноты в редакторах пишутся как `C4`, `D#5`, `OFF`. `OFF` глушит канал. Пустая клетка паттерна ноту держит.

Сэмпловый микшер работает на хосте и не привязан к такту THOTH. Секвенсор привязан. Строка паттерна стоит 48 тактов. Клетка, которая берёт ноту или шлёт `OFF`, стоит ещё 8. Удержание ничего не добавляет. Эти такты прибавляются после среза процессора и всё ещё могут сделать кадр LATE.

Октава в редакторе: `,` и `.` или `-` и `=`. Ноты — ряд `Z X C V B N M`, полутона — `S D G H J`.

## Такты

THOTH сначала ставит цену инструкции, потом добавляет ожидание по адресу каждого обращения к данным:

| Область | Лишние такты |
| --- | --- |
| SRAM, волновая память | 0 |
| ПЗУ кассеты, только данные | +1 |
| Кадровый буфер, палитра, порты PPU, APU, пада и системы | +2 |

Выборка команды уже входит в объявленную цену. Второй раз она не считается. Кэша и конвейера нет, поэтому взятая ветка не сбрасывает то, что никто не выбирал заранее.

Бюджет кадра — 333333 тактов, каждый третий кадр — 333334. Завершение — это ожидание среды (`WFI` ставится после `_draw`, если ваш код вернулся). Если бюджет превышен или процессор всё ещё работает, кадр LATE, и перерасход вычитается из следующего.

`cycles()` читает такты процессора в текущем кадре и не включает стоимость секвенсора, которую прибавляют уже после остановки CPU.

## Прочее

| Вызов | Смысл |
| --- | --- |
| `print(v)` | Строка в журнал консоли, не на экран |
| `frame()` | Номер кадра |
| `cycles()` | Такты CPU в этом кадре на данный момент |
| `rnd(n)` | Целое от 0 до n−1 |
| `abs` `min` `max` | Как ожидается, на целых |
| `peek(addr)` `poke(addr, v)` | Байт SRAM. Порты PPU и APU так не трогают: у них свои вызовы |

`Ctrl+S` пишет кассету в каталог `carts` рядом с проектом или рядом с exe. Имя — буквы, цифры, `-` и `_`. `Ctrl+P` понимает `run`, `new`, `save имя`, `load имя`.

`python -m argonaut carts/ferry.alc` сразу запускает этот файл, минуя ожидание в редакторе. Esc возвращает назад.
