#!/usr/bin/env python3
"""Versión pública y sin estado del chequeador de riesgo de discontinuación
en Scopus. Cualquiera puede chequear un ISSN puntual; nada se guarda —no hay
watchlist compartida, no hay historial persistente entre visitantes. Pensada
para desplegarse en un hosting público (ver render.yaml / README).
"""
from flask import Flask, render_template_string, request

from core import evaluate_journal

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except ImportError:  # flask-limiter es opcional para uso local
    Limiter = None

app = Flask(__name__)

if Limiter:
    limiter = Limiter(get_remote_address, app=app, default_limits=["30 per hour", "6 per minute"])

COLOR_POR_NIVEL = {
    "Bajo": "#1a7f37",
    "Medio": "#9a6700",
    "Medio-alto": "#bc4c00",
    "Alto": "#cf222e",
}

PAGE = """
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>¿Está en riesgo tu revista en Scopus?</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body { font-family: -apple-system, Arial, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; color: #1f2328; }
  h1 { font-size: 1.4rem; }
  form { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 1rem 0 1.5rem; padding: 1rem; background: #f6f8fa; border-radius: 8px; }
  input { padding: 0.5rem; border: 1px solid #d0d7de; border-radius: 6px; }
  input[name=issn] { width: 160px; }
  input[name=nombre] { flex: 1; min-width: 200px; }
  button { padding: 0.5rem 1rem; border: 1px solid #1f6feb; background: #1f6feb; color: white; border-radius: 6px; cursor: pointer; }
  .badge { display: inline-block; padding: 0.2rem 0.8rem; border-radius: 999px; color: white; font-size: 1rem; }
  .razones { margin: 0.6rem 0 0; padding-left: 1.2rem; }
  .error { background: #ffebe9; border: 1px solid #ff8182; padding: 0.6rem 1rem; border-radius: 6px; }
  table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; font-size: 0.85rem; }
  th, td { text-align: left; padding: 0.3rem 0.5rem; border-bottom: 1px solid #eaeef2; }
  h4 { margin: 1rem 0 0.2rem; font-size: 0.8rem; color: #57606a; text-transform: uppercase; }
  small.hint { color: #57606a; }
  .aviso { background: #fff8c5; border: 1px solid #d4a72c; padding: 0.7rem 1rem; border-radius: 6px; font-size: 0.85rem; margin-bottom: 1.5rem; }
  .chart-wrap { max-width: 480px; margin-top: 0.5rem; }
  footer { margin-top: 2rem; font-size: 0.8rem; color: #57606a; }
</style>
</head>
<body>
  <h1>¿Está en riesgo tu revista en Scopus?</h1>
  <p><small class="hint">Chequea un ISSN antes de enviar o aceptar un artículo. No es un servicio oficial de Scopus/Elsevier.</small></p>

  <div class="aviso">
    Esto NO es una predicción certera de exclusión — ningún sistema anuncia
    una baja de Scopus antes que Scopus mismo. Son señales de riesgo (estado
    oficial, tendencias de SJR/cuartil, retractaciones, volumen de
    publicación) para decidir con más cautela. Nada de lo que ingreses aquí
    se guarda.
  </div>

  <form method="post" action="/">
    <input type="text" name="issn" placeholder="ISSN (ej. 1234-5678)" value="{{ issn or '' }}" required>
    <input type="text" name="nombre" placeholder="Nombre de la revista (opcional)" value="{{ nombre or '' }}">
    <button type="submit">Chequear</button>
  </form>

  {% if error %}
    <div class="error">{{ error }}</div>
  {% endif %}

  {% if r %}
    <h2>{{ r.nombre }} <span class="badge" style="background:{{ colores[r.score] }}">{{ r.score }}</span></h2>
    <ul class="razones">
      {% for razon in r.razones %}<li>{{ razon }}</li>{% endfor %}
    </ul>

    {% set d = r.detalle %}
    <h4>Scopus Source List</h4>
    {% if d.scopus and d.scopus.encontrada %}
      Estado: <strong>{{ d.scopus.estado or "-" }}</strong> ·
      Cobertura: {{ d.scopus.cobertura or "-" }} ·
      Editorial: {{ d.scopus.editorial or "-" }}
      {% if d.scopus.sourcerecord_id %}
        <br><a target="_blank" rel="noopener" href="https://www.scopus.com/sourceid/{{ d.scopus.sourcerecord_id }}#tabs=1">Ver CiteScore/cuartil oficial en Scopus ↗</a>
      {% endif %}
    {% else %}
      No aparece en el Scopus Source List actual.
    {% endif %}

    <h4>Histórico SCImago (SJR / cuartil estimado)</h4>
    {% if d.scimago and d.scimago.encontrada %}
      <div class="chart-wrap"><canvas id="chart" height="220"></canvas></div>
      <script>
        var historia = {{ d.scimago.historia|tojson }};
        new Chart(document.getElementById("chart"), {
          type: "line",
          data: {
            labels: historia.map(function(h){ return h.anio; }),
            datasets: [
              { label: "SJR", data: historia.map(function(h){ return h.sjr; }), borderColor: "#1f6feb", backgroundColor: "#1f6feb", yAxisID: "y_sjr", spanGaps: true },
              { label: "Cuartil estimado", data: historia.map(function(h){ return h.cuartil; }), borderColor: "#bc4c00", backgroundColor: "#bc4c00", yAxisID: "y_cuartil", spanGaps: true }
            ]
          },
          options: {
            responsive: true,
            scales: {
              y_sjr: { type: "linear", position: "left", title: { display: true, text: "SJR" } },
              y_cuartil: { type: "linear", position: "right", reverse: true, min: 1, max: 4, ticks: { stepSize: 1, callback: function(v){ return "Q"+v; } }, title: { display: true, text: "Cuartil (mejor arriba)" }, grid: { drawOnChartArea: false } }
            }
          }
        });
      </script>
      <small class="hint">Cuartil estimado por nosotros (ranking de SJR por categoría ASJC), no es el oficial de Scopus.</small>
    {% else %}
      Sin datos en el dataset de SCImago.
    {% endif %}

    <h4>Volumen de artículos por año (Crossref)</h4>
    {% if d.volumen and d.volumen.consultada %}
      <table>
        <tr>{% for h in d.volumen.historia %}<th>{{ h.anio }}{{ "*" if h.anio == d.volumen.anio_actual_parcial else "" }}</th>{% endfor %}</tr>
        <tr>{% for h in d.volumen.historia %}<td>{{ h.documentos if h.documentos is not none else "-" }}</td>{% endfor %}</tr>
      </table>
      <small class="hint">*Año en curso, incompleto.</small>
    {% else %}
      No se pudo consultar.
    {% endif %}

    <h4>Retractaciones (Crossref / Retraction Watch)</h4>
    {% if d.retractions and d.retractions.consultada %}
      {{ d.retractions.recientes|length }} en los últimos 24 meses ({{ d.retractions.total_historico }} en total histórico).
    {% else %}
      No se pudo consultar.
    {% endif %}
  {% endif %}

  <footer>
    Proyecto de código abierto —
    <a href="https://github.com/dsornoza/RevistasScopus" target="_blank" rel="noopener">código en GitHub</a>.
    Fuentes: Scopus Source List oficial, dataset comunitario de SCImago, Crossref.
    No afiliado a Elsevier/Scopus.
  </footer>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method != "POST":
        return render_template_string(PAGE, r=None, error=None, issn=None, nombre=None, colores=COLOR_POR_NIVEL)

    issn = request.form.get("issn", "").strip()
    nombre = request.form.get("nombre", "").strip()
    if not issn:
        return render_template_string(
            PAGE, r=None, error="Ingresa un ISSN.", issn=issn, nombre=nombre, colores=COLOR_POR_NIVEL
        )

    resultado = evaluate_journal(issn, nombre)
    return render_template_string(
        PAGE, r=resultado, error=None, issn=issn, nombre=nombre, colores=COLOR_POR_NIVEL
    )


if __name__ == "__main__":
    app.run(debug=False, port=5001)
