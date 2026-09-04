# 🌡️ Barometr Ryzyka Finansowego

Automatyczny monitor napięcia w systemie finansowym + **aplikacja na telefon (PWA)**.

## Instalacja na telefonie

Po opublikowaniu na GitHub Pages otwórz stronę na telefonie:

### Android (Chrome)
Menu ⋮ → **Zainstaluj aplikację** (lub baner „Zainstaluj”).

### iPhone (Safari)
**Udostępnij** (□↑) → **Dodaj do ekranu początkowego** → Dodaj.

Ikona „Barometr” pojawi się na pulpicie i otwiera się jak zwykła apka.

## Deploy na GitHub

1. Nowe publiczne repo, np. `crisis-barometer`
2. Wgraj **zawartość** tego folderu do głównego katalogu (w tym `.github`)
3. Secret: Settings → Secrets → Actions → `FRED_API_KEY`
4. Pages: Settings → Pages → main / root
5. Actions → **Aktualizuj Barometr Ryzyka** → Run workflow

Adres: `https://TWOJA_NAZWA.github.io/crisis-barometer/`

## Co mierzy
VIX, krzywa rentowności, spready HY, NFCI, rynki, newsy, próbka SEC 8-K → wynik 0–100.

To nie jest porada inwestycyjna.
