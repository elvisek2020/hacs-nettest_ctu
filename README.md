# NetTest ČTÚ pro Home Assistant

Custom integrace pro Home Assistant, která měří rychlost internetového připojení
proti měřicí infrastruktuře **NetTest ČTÚ** ([nettest.ctu.gov.cz](https://nettest.ctu.gov.cz))
pomocí protokolu **RMBT**. Výsledky vystaví jako senzory a jde je spustit ručně
i na interval.

> ## Upozornění
>
> Tohle je **neoficiální** integrace. Nemá žádnou vazbu na Český telekomunikační
> úřad, není jím vyvíjená ani podporovaná.
>
> **Výsledek měření je orientační a není certifikovaným měřením.** Pro reklamaci
> rychlosti u poskytovatele je potřeba certifikované měření, které vyžaduje
> kabelové připojení přímo do koncového zařízení a musí proběhnout přes
> oficiální aplikaci nebo web ČTÚ. Měření z Home Assistantu běží po vaší domácí
> síti, typicky přes Wi-Fi a s dalším provozem na lince, takže výsledek pro
> reklamaci použít nelze.

## Co integrace umí

![Stránka zařízení NetTest ČTÚ v Home Assistantu se senzory rychlosti, pingu a průměrů](https://raw.githubusercontent.com/elvisek2020/hacs-nettest_ctu/main/images/device-page.jpg)

| Entita | Jednotka | Popis |
|---|---|---|
| `sensor.nettest_ctu_download` | Mbit/s | rychlost stahování |
| `sensor.nettest_ctu_upload` | Mbit/s | rychlost odesílání |
| `sensor.nettest_ctu_ping` | ms | nejkratší naměřený ping |
| `sensor.nettest_ctu_jitter` | ms | rozptyl pingu (viz níže) |
| `sensor.nettest_ctu_last_test` | timestamp | čas posledního dokončeného měření |
| `sensor.nettest_ctu_average_download` | Mbit/s | průměrný download z posledních N měření |
| `sensor.nettest_ctu_average_upload` | Mbit/s | průměrný upload z posledních N měření |
| `binary_sensor.nettest_ctu_test_running` | on/off | probíhá měření |
| `button.nettest_ctu_run_test` | — | spustí měření mimo nastavený interval |

Měření jde spustit i akcí `ctu_nettest.run_test`, což je to samé jako stisk
tlačítka — hodí se v automatizacích a skriptech.

> Instalace založené před verzí 0.2.1 mají senzory pojmenované ještě podle
> původního názvu, tedy s prefixem `sensor.ctu_nettest_`. Přejmenování názvu
> integrace už existující entity nepřejmenovalo, aby se nerozbily dashboardy
> a automatizace. Tlačítko je nové, takže má prefix `nettest_ctu_` všude.

Doplňující údaje jsou v atributech entit: počet vláken, přenesené bajty, medián
pingu, počet vzorků, adresa měřicího serveru a délka testu. Veřejná IP adresa se
**záměrně nevystavuje**, i když ji control server v odpovědi posílá.

Průměrové senzory mají v atributech `sample_count` (z kolika měření je průměr
spočítaný), `sample_window` (nastavený počet měření) a `oldest_sample` (čas
nejstaršího započítaného měření).

## Požadavky

- Home Assistant 2024.12 nebo novější
- Žádná Java, žádné externí binárky. Integrace používá PyPI balíček
  [`rmbt-client`](https://pypi.org/project/rmbt-client/), který je čistě
  v Pythonu, takže funguje na **Home Assistant OS, Container i Core**.

## Instalace

### HACS (custom repository)

1. HACS → tři tečky vpravo nahoře → **Custom repositories**
2. Repository: `https://github.com/elvisek2020/hacs-nettest_ctu`, kategorie **Integration**
3. Najdi **NetTest ČTÚ**, dej **Download**
4. Restartuj Home Assistant
5. **Nastavení → Zařízení a služby → Přidat integraci → NetTest ČTÚ**

### Manuálně

1. Zkopíruj `custom_components/ctu_nettest` do `<config>/custom_components/ctu_nettest`
2. Restartuj Home Assistant
3. Přidej integraci přes **Nastavení → Zařízení a služby**

## Konfigurace

| Položka | Default | Popis |
|---|---|---|
| URL control serveru | `https://nettest.ctu.gov.cz/RMBTControlServer` | Měň jen pokud provozuješ vlastní RMBT infrastrukturu. |
| Interval měření | 30 min | Zadává se v minutách, minimum je 10 a maximum 10080 (7 dní). Měření plně vytíží linku, drž interval co nejvyšší. |
| Měřit automaticky | zapnuto | Když vypneš, měření se spustí jen akcí `ctu_nettest.run_test`. |
| Počet měření pro průměry | 10 | Z kolika posledních měření se počítají průměrný download a upload. |

Všechno se dá později změnit v **Konfigurovat** u integrace. Změna nastavení
nespustí měření — nový interval i nový počet měření pro průměry se aplikují za
běhu.

Pozor na objem dat: jedno měření přenese stovky megabajtů, takže třeba interval
30 minut znamená 48 měření denně a řádově desítky gigabajtů měsíčně. Na měřeném
tarifu volte interval odpovídajícím způsobem.

Instalace nastavené ve starší verzi, kde se interval zadával v hodinách, se
převedou automaticky (12 h se stane 720 min), není potřeba nic přenastavovat.

### Limity na straně ČTÚ

ČTÚ nikde nepublikuje pravidla pro automatizované měření, ale jeho vlastní režim
[Opakované měření](https://nettest.ctu.gov.cz/cs/Loop) si zadané hodnoty ořezává.
Podle zdrojového kódu webu
([`src/js/Loop.js`](https://github.com/CTUCZ/nettest-rmbt-website/blob/main/src/js/Loop.js)):

| Parametr | Mez v oficiálním klientovi ČTÚ |
|---|---|
| nejkratší interval mezi testy | 10 minut |
| nejdelší interval mezi testy | 48 hodin |
| počet testů ve smyčce | 1 až 500 |

Minimální interval této integrace je proto také 10 minut, aby nešel pod hranici,
kterou ČTÚ dává vlastním uživatelům. Rozdíl zůstává v tom, že oficiální smyčka
vždy skončí, zatímco integrace měří bez omezení počtu testů.

Control server ČTÚ ([CTUCZ/open-rmbt](https://github.com/CTUCZ/open-rmbt)) žádnou
z těchto mezí nevynucuje — kód pro odmítnutí opakovaného měření
(`LoopModeRejectedException` v `RegistrationResource.java`) je ve zveřejněné verzi
neaktivní a jiné omezení počtu požadavků tam není. Protokol RMBT má ale vlastní
pojistku proti přetížení: token z `testRequest` nese čas, odkdy klient smí měřit,
a při vytížení může control server start odložit. Integrace toto čekání
respektuje.

Hodnoty odpovídají stavu k srpnu 2026, ověřovat je vždy proti odkazovaným
zdrojům ČTÚ.

Historie měření pro průměry se drží mimo recorder, ve vlastním úložišti
Home Assistantu (`.storage`), takže přežije restart a nezávisí na tom, jak
dlouho ti recorder drží historii. Plnit se ale začne až od instalace verze,
která průměry umí — starší výsledky se zpětně nedotahují. Než se nasbírá N
měření, průměr se počítá z toho, co je k dispozici.

Měření se nikdy nespustí během startu Home Assistantu, ale až po jeho dokončení.

## Příklad automatizace

Měření každý den ve 3:00 a upozornění, když download spadne pod 50 Mbit/s:

```yaml
automation:
  - alias: Noční test rychlosti
    triggers:
      - trigger: time
        at: "03:00:00"
    actions:
      - action: ctu_nettest.run_test

  - alias: Upozornění na pomalou linku
    triggers:
      - trigger: numeric_state
        entity_id: sensor.nettest_ctu_download
        below: 50
    actions:
      - action: notify.persistent_notification
        data:
          title: Pomalé připojení
          message: >-
            Download je jen {{ states('sensor.nettest_ctu_download') }} Mbit/s
            (ping {{ states('sensor.nettest_ctu_ping') }} ms).
```

## Příklad dashboard karty

```yaml
type: vertical-stack
cards:
  - type: entities
    title: NetTest ČTÚ
    entities:
      - entity: sensor.nettest_ctu_download
      - entity: sensor.nettest_ctu_upload
      - entity: sensor.nettest_ctu_ping
      - entity: sensor.nettest_ctu_jitter
      - entity: sensor.nettest_ctu_last_test
      - entity: binary_sensor.nettest_ctu_test_running
  - type: button
    entity: button.nettest_ctu_run_test
    name: Změřit teď
  - type: history-graph
    hours_to_show: 168
    entities:
      - entity: sensor.nettest_ctu_download
      - entity: sensor.nettest_ctu_upload
```

## Jak to funguje

```
POST /RMBTControlServer/settings     → registrace klienta, klientské UUID
POST /RMBTControlServer/testRequest  → token, adresa měřicího serveru, parametry
pre-test                             → zjištění velikosti chunku a počtu vláken
ping                                 → 10–100 vzorků
download                             → N vláken paralelně, ~10 s
upload                               → N vláken paralelně, ~10 s
```

Jedno měření trvá přibližně půl minuty a po celou dobu plně vytíží linku.
Klientské UUID se ukládá do konfigurace integrace a používá se opakovaně, aby
ČTÚ nezakládal nový klientský záznam při každém měření.

## Známá omezení

- **Výsledky se na ČTÚ neodesílají.** Pravidelné automatické měření by
  zaplevelovalo veřejná otevřená data ČTÚ. Důsledkem je, že měření nenajdeš
  v historii na webu ČTÚ a na jejich straně zůstane záznam testu bez výsledku,
  stejně jako u přerušeného měření.
- **Měření běží v pure Pythonu.** Balíček `rmbt-client` má volitelné C rozšíření,
  ale publikuje pro něj wheels jen pro `manylinux`, což na Alpine/musl kontejneru
  Home Assistantu nesedí. Instalace proto spadne zpět na pure-Python variantu.
  Pro běžné domácí přípojky je to dostatečné, u velmi rychlých linek (řádově
  gigabity) může výsledek podstřelovat.
- **Není certifikované měření.** Viz upozornění na začátku.
- Nejde o pasivní senzor: každé měření reálně přenese stovky MB dat. Pozor při
  měřeném datovém tarifu.

## Vývoj

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest          # testy, žádný provoz proti ČTÚ
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

## Licence a poděkování

Apache License 2.0 — viz [LICENSE](LICENSE), konzistentně s upstream RMBT.

Postaveno na těchto open-source projektech:

- [RMBT specifikace](https://github.com/rtr-nettest/rmbt-server/blob/master/RMBT_specification.md) (RTR-Netztest)
- [`rmbt-client`](https://github.com/raaaimund/open-rmbt-client-cli) — Python RMBT klient
- [CTUCZ](https://github.com/CTUCZ) — fork RMBT infrastruktury pro ČR
