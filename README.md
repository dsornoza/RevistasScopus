# Alerta de riesgo de discontinuación en Scopus

Herramienta personal para detectar señales de riesgo de que una revista sea
removida de Scopus, antes de confiar en ella para publicar. No puede
adelantarse con certeza a Scopus (su lista oficial es la única fuente de
verdad y se actualiza mensualmente), pero cruza esa lista con el histórico de
SJR y con retractaciones recientes para dar una alerta temprana.

## Instalación

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp watchlist.example.json watchlist.json
```

`watchlist.json` es tuyo y personal — no se versiona (está en `.gitignore`)
porque revela qué revistas has usado, incluidas las que te preocupan. Cada
quien que clone este repo empieza con `watchlist.example.json` como base.

## App pública (sin estado)

Además del dashboard personal (con tu watchlist), `src/public_app.py` es una
versión pública de una sola página: cualquiera puede chequear un ISSN, pero
**nada se guarda** — no hay watchlist compartida ni historial entre
visitantes, así que no hace falta login para protegerla. Tiene rate limit
(30 chequeos/hora por IP) para no abusar de Scopus/Crossref.

**Desplegar en Render.com** (plan gratuito):

1. Crea una cuenta en [render.com](https://render.com) — puedes entrar con tu
   cuenta de GitHub directamente, no hace falta tarjeta para el plan free.
2. En el dashboard de Render: **New +** → **Blueprint**.
3. Conecta tu cuenta de GitHub si te lo pide, y selecciona el repo
   `dsornoza/RevistasScopus`.
4. Render detecta automáticamente `render.yaml` en la raíz del repo y
   propone crear el servicio `revistas-scopus-checker`. Confirma con
   **Apply**.
5. El primer build tarda unos minutos porque descarga el Scopus Source List
   (~20MB) y el dataset de SCImago (~85MB) *durante el build* — a propósito,
   así el servicio no se traba la primera vez que alguien lo visita después
   de estar dormido (el plan free se duerme tras 15 min sin tráfico).
6. Cuando termine, Render te da una URL pública tipo
   `https://revistas-scopus-checker.onrender.com` — esa es la que compartes.

Los datos cacheados se refrescan en cada redeploy de Render, y por separado
el GitHub Action mensual mantiene los archivos fuente actualizados en el
repo (ver sección de abajo) — si quieres que Render también recoja esos
refreshes automáticamente, puedes activar "Auto-Deploy" en la configuración
del servicio para que redespliegue cada vez que el Action haga push.

## Uso

**Dashboard web** (recomendado para uso diario):

```bash
./.venv/bin/python src/dashboard.py
```

Abre `http://127.0.0.1:5000`. Tiene un formulario para agregar una revista por
ISSN (el nombre se autocompleta desde Scopus/SCImago si lo dejas en blanco),
una tabla con el riesgo actual de cada revista de tu watchlist, botón
"Revisar ahora" por fila, y botón para quitarla. Es solo para uso local (no
lo expongas a internet, es un servidor de desarrollo sin autenticación).

**Chequeo puntual de una revista** (antes de enviar o aceptar un artículo):

```bash
./.venv/bin/python src/check_journal.py --issn 1234-5678 --nombre "Nombre de la revista"
```

**Monitoreo de tu lista de revistas**: edita `watchlist.json` con las revistas
que te interesan (donde ya publicaste o consideras publicar), luego corre:

```bash
./.venv/bin/python src/monitor_watchlist.py
```

Esto genera `reports/YYYY-MM.md` con un resumen de todas, y una sección
`## ALERTAS` si el riesgo de alguna subió desde la última corrida. Los
snapshots quedan en `data/history/<issn>.jsonl` para comparar corridas futuras.

Para no tener que acordarte de correrlo, puedes programarlo mensualmente
(coincide con la cadencia de actualización del Scopus Source List) usando la
skill `schedule` de Claude Code, apuntando al comando de arriba.

## Datos cacheados: refresh mensual automático

Un GitHub Action (`.github/workflows/refresh-data.yml`) corre el día 5 de cada
mes y descarga el Scopus Source List oficial y el dataset de SCImago más
recientes. Solo publica un nuevo release (`data-YYYY-MM` en
[Releases](../../releases)) si el archivo realmente cambió — `data/latest.json`
registra la fecha y el hash de la última versión de cada fuente. Esto importa
porque **Scopus actualiza su lista mensualmente, pero SCImago solo publica
datos nuevos una vez al año (abril–junio)**: la mayoría de los meses el
refresh no encontrará cambios en SCImago, y eso es lo esperado, no un fallo.

Puedes disparar un refresh manual desde la pestaña Actions del repo
("Run workflow"), o localmente con:

```bash
./.venv/bin/python scripts/refresh_cached_data.py
```

(requiere `gh auth login` con permiso de escritura sobre el repo).

## Fuentes usadas y sus límites

- **Scopus Source List oficial** (Elsevier): fuente de verdad, descarga
  automática y gratuita, sin login. Se actualiza ~mensualmente.
- **SCImago**: `scimagojr.com` bloquea cualquier acceso automatizado
  (Cloudflare, probado con requests y curl). En su lugar se usa el dataset
  comunitario de Michael E. Rose que republica el histórico de SJR/h-index,
  con menos columnas (no incluye cuartil, volumen de documentos ni
  autocitación) y actualización no en tiempo real.
- **Retracciones**: API pública de Crossref (integra Retraction Watch desde
  2023), gratis y sin key.
- **Volumen de artículos por año**: también vía Crossref (conteo de works por
  ISSN y año). Detecta el patrón de "explosión de volumen" descrito en
  revistas bajo revisión CSAB de Scopus (ej. una revista que pasa de ~5 a
  ~2000 artículos/año, o publica en 8 meses más que en todo el año anterior).
- **CiteScore/cuartil oficial y estado "on hold/CSAB"**: NO son automatizables.
  Viven detrás de un Cloudflare bot-check en scopus.com incluso en modo
  "preview" sin cuenta — no vamos a construir un scraper que lo sortee. El
  dashboard sí calcula un cuartil *estimado* (ranking de SJR por categoría
  ASJC) y trae un botón que abre la página oficial de Scopus en tu navegador
  para que la revises tú mismo cuando quieras el dato real.
- **Señales de comunidad** (foros, listas de revistas cuestionadas): no
  automatizadas por falta de una fuente gratuita confiable. Si quieres,
  pídeme una búsqueda puntual para una revista específica.

⚠️ Herramientas de terceros tipo "AI Journal Risk Analyzer" que aparecen en
blogs de reseñas (ej. contenido patrocinado de Futurity Publishing/Arxivia):
trátalas con escepticismo — son cajas negras sin metodología pública, y el
artículo que las promociona es en el fondo marketing. No están integradas
aquí ni lo estarán sin poder verificar cómo calculan su veredicto.

## Interpretación del score

- **Alto**: la revista ya figura "Inactive" en Scopus (o no aparece en el
  listado actual), el dataset de SCImago la marca "(discontinued)", explosión
  de volumen de artículos (≥3x interanual, o el año en curso ya supera el
  año completo anterior).
- **Medio-alto**: caída de SJR >30% interanual, caída de 2+ cuartiles, SJR
  faltante en el último año, ≥2 retractaciones en 24 meses, cambio de
  editorial, o crecimiento de volumen ≥1.5x.
- **Medio**: 1 retractación reciente, caída de 1 cuartil, o declive sostenido
  de citas por documento en 3 años.
- **Bajo**: sin señales detectadas.

Cada score viene con las razones concretas — revísalas, el número solo no
basta para decidir.
