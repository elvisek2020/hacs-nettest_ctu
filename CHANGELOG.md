# Changelog

Poznámky k vydání. Sekce `## vX.Y.Z` se při releasu automaticky použije jako
text vydání na GitHubu — a ten Home Assistant / HACS ukazuje v okně aktualizace.

Nejnovější verze je nahoře. Starší historie je v [GitHub releases](https://github.com/elvisek2020/hacs-nettest_ctu/releases).

## v0.5.1 — 2026-10-12

### ⚠️ Změny, které vyžadují zásah

- Integrace nově vyžaduje **Home Assistant 2026.3 nebo novější**. Od této verze HA zobrazuje ikonu integrace přímo z repozitáře. Na starším HA ti HACS tuhle ani další verze nenabídne.

### ✨ Novinky

- Licence je nově **MIT** místo Apache 2.0.
- README má přehlednější strukturu, štítky a tlačítko „Otevřít v HACS“.
- Vydání verzí vytváří GitHub Actions, text vydání se bere z tohoto changelogu.

Funkce integrace se nemění, aktualizace nevyžaduje žádné přenastavení.

## v0.5.0 — 2026-08-23

### ✨ Novinky

- Nová entita **`button.nettest_ctu_run_test`** („Spustit měření“). Objeví se přímo na stránce zařízení, takže měření spustíš jedním klikem bez skládání dashboard karty.
- Tlačítko dělá přesně to samé co akce `ctu_nettest.run_test`, která zůstává k dispozici pro automatizace a skripty.
- Tlačítko zůstává dostupné i po neúspěšném měření, aby šel pokus z UI zopakovat. Selhání se ohlásí jako chyba v UI.
- Stisk během probíhajícího měření druhé měření nespustí, jen se zapíše varování do logu.
- README má nově screenshot stránky zařízení.

### 🐛 Opravy

- README uvádělo ID entit s prefixem `sensor.ctu_nettest_`, ale instalace je od přejmenování integrace na „NetTest ČTÚ“ dostávají jako `sensor.nettest_ctu_`. Všechna ID v dokumentaci jsou sjednocená na aktuální podobu.
- Instalace založené před verzí 0.2.1 si původní prefix `ctu_nettest_` u stávajících senzorů drží dál. V README je na to poznámka.
