# 🌡️ Barometr Ryzyka Finansowego

Automatyczny monitor napięcia w systemie finansowym.
Co ~6 godzin zbiera wskaźniki makro (FRED), rynki, newsy i sygnały SEC,
liczy wynik **0–100** i publikuje prosty dashboard.

To **nie** jest prognoza daty kryzysu ani porada inwestycyjna.

## Szybki start (GitHub)

### 1. Nowe repozytorium
Utwórz publiczne repo, np. `crisis-barometer`.

### 2. Wgraj pliki
Wgraj **zawartość** tego folderu do **głównego katalogu** repozytorium
(index.html, crisis_monitor.py, .github, monitor_data, ...).

### 3. Dodaj sekret z kluczem FRED
1. Repo → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret**
3. Name: `FRED_API_KEY`
4. Value: wklej swój klucz z FRED
5. Save

### 4. Włącz GitHub Pages
Settings → Pages → Source: branch `main`, folder `/ (root)` → Save

Adres:
`https://TWOJA_NAZWA.github.io/crisis-barometer/`

### 5. Pierwsze uruchomienie
Actions → **Aktualizuj Barometr Ryzyka** → **Run workflow**

Po zielonym statusie odśwież stronę.

## Co jest mierzone
- VIX / strach
- Krzywa rentowności (10y–2y)
- Spready high-yield
- Warunki finansowe NFCI
- Ruch indeksów i sektora finansowego
- Nagłówki o stresie
- Próbka 8-K z SEC

## Automatyzacja
Workflow odpala się sam co 6 godzin + ręcznie przez Run workflow.
