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

| Entita | Jednotka | Popis |
|---|---|---|
| `sensor.ctu_nettest_download` | Mbit/s | rychlost stahování |
| `sensor.ctu_nettest_upload` | Mbit/s | rychlost odesílání |
| `sensor.ctu_nettest_ping` | ms | nejkratší naměřený ping |
| `sensor.ctu_nettest_jitter` | ms | rozptyl pingu (viz níže) |
| `sensor.ctu_nettest_last_test` | timestamp | čas posledního dokončeného měření |
| `binary_sensor.ctu_nettest_test_running` | on/off | probíhá měření |

Akce `ctu_nettest.run_test` spustí měření mimo nastavený interval.

Doplňující údaje jsou v atributech entit: počet vláken, přenesené bajty, medián
pingu, počet vzorků, adresa měřicího serveru a délka testu. Veřejná IP adresa se
**záměrně nevystavuje**, i když ji control server v odpovědi posílá.

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
| Interval měření | 12 h | Měření plně vytíží linku, drž interval vysoko. |
| Měřit automaticky | zapnuto | Když vypneš, měření se spustí jen akcí `ctu_nettest.run_test`. |

Všechno se dá později změnit v **Konfigurovat** u integrace. Změna nastavení
nespustí měření — nový interval se aplikuje za běhu.

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
        entity_id: sensor.ctu_nettest_download
        below: 50
    actions:
      - action: notify.persistent_notification
        data:
          title: Pomalé připojení
          message: >-
            Download je jen {{ states('sensor.ctu_nettest_download') }} Mbit/s
            (ping {{ states('sensor.ctu_nettest_ping') }} ms).
```

## Příklad dashboard karty

```yaml
type: vertical-stack
cards:
  - type: entities
    title: NetTest ČTÚ
    entities:
      - entity: sensor.ctu_nettest_download
      - entity: sensor.ctu_nettest_upload
      - entity: sensor.ctu_nettest_ping
      - entity: sensor.ctu_nettest_jitter
      - entity: sensor.ctu_nettest_last_test
      - entity: binary_sensor.ctu_nettest_test_running
  - type: button
    name: Změřit teď
    icon: mdi:speedometer
    tap_action:
      action: perform-action
      perform_action: ctu_nettest.run_test
  - type: history-graph
    hours_to_show: 168
    entities:
      - entity: sensor.ctu_nettest_download
      - entity: sensor.ctu_nettest_upload
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

- **Výsledky se na ČTÚ neodesílají.** Automatické měření každých 12 hodin by
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
