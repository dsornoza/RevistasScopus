#!/usr/bin/env python3
"""Dashboard web local para monitorear riesgo de discontinuación en Scopus.

Uso:
    python src/dashboard.py
    (abre http://127.0.0.1:5000 en el navegador)
"""
import json

from flask import Flask, render_template_string, request, redirect, url_for, flash

from core import (
    evaluate_journal,
    save_snapshot,
    last_snapshot,
    load_watchlist,
    add_journal,
    remove_journal,
    update_journal_nombre,
)

app = Flask(__name__)
app.secret_key = "revistas-scopus-dashboard"  # solo para flash messages locales

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
<title>Riesgo de discontinuación en Scopus</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body { font-family: -apple-system, Arial, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1f2328; }
  h1 { font-size: 1.4rem; }
  form.add-form { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 1rem 0 2rem; padding: 1rem; background: #f6f8fa; border-radius: 8px; }
  form.add-form input { padding: 0.4rem; border: 1px solid #d0d7de; border-radius: 6px; }
  form.add-form input[name=issn] { width: 140px; }
  form.add-form input[name=nombre] { flex: 1; min-width: 200px; }
  button { padding: 0.4rem 0.9rem; border: 1px solid #1f6feb; background: #1f6feb; color: white; border-radius: 6px; cursor: pointer; }
  button.secundario { background: white; color: #1f6feb; }
  button.peligro { background: white; color: #cf222e; border-color: #cf222e; }
  table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
  th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid #d0d7de; vertical-align: top; }
  .badge { display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; color: white; font-size: 0.85rem; }
  .razones { font-size: 0.85rem; color: #57606a; margin: 0.3rem 0 0; padding-left: 1.1rem; }
  .flash { background: #ddf4ff; border: 1px solid #54aeff; padding: 0.6rem 1rem; border-radius: 6px; margin-bottom: 1rem; }
  .acciones form { display: inline; }
  small.hint { color: #57606a; }
  details.detalle { margin-top: 0.5rem; font-size: 0.85rem; }
  details.detalle summary { cursor: pointer; color: #1f6feb; }
  details.detalle table { margin-top: 0.5rem; }
  details.detalle th, details.detalle td { padding: 0.2rem 0.5rem; border-bottom: 1px solid #eaeef2; font-size: 0.8rem; }
  details.detalle h4 { margin: 0.6rem 0 0.2rem; font-size: 0.8rem; color: #57606a; text-transform: uppercase; }
  .chart-wrap { max-width: 480px; margin-top: 0.5rem; }
  a.link-externo { font-size: 0.8rem; }
</style>
</head>
<body>
  <h1>Riesgo de discontinuación en Scopus</h1>
  <p><small class="hint">Chequea revistas antes de publicar y monitorea las que ya tienes en tu watchlist.</small></p>

  {% for msg in get_flashed_messages() %}
    <div class="flash">{{ msg }}</div>
  {% endfor %}

  <form class="add-form" method="post" action="{{ url_for('agregar') }}">
    <input type="text" name="issn" placeholder="ISSN (ej. 1234-5678)" required>
    <input type="text" name="nombre" placeholder="Nombre de la revista (opcional)">
    <button type="submit">Agregar y chequear</button>
  </form>

  <table>
    <tr><th>Revista</th><th>ISSN</th><th>Riesgo</th><th>Último chequeo</th><th>Acciones</th></tr>
    {% for r in filas %}
    <tr>
      <td>{{ r.nombre or r.issn }}</td>
      <td>{{ r.issn }}</td>
      <td>
        {% if r.score %}
          <span class="badge" style="background:{{ colores[r.score] }}">{{ r.score }}</span>
          {% if r.razones %}
            <ul class="razones">
              {% for razon in r.razones %}<li>{{ razon }}</li>{% endfor %}
            </ul>
          {% endif %}
          {% set d = r.detalle %}
          {% if d %}
          <details class="detalle">
            <summary>Ver detalle de indicadores</summary>

            <h4>Scopus Source List</h4>
            {% if d.scopus and d.scopus.encontrada %}
              Estado: <strong>{{ d.scopus.estado or "-" }}</strong> ·
              Cobertura: {{ d.scopus.cobertura or "-" }} ·
              Editorial: {{ d.scopus.editorial or "-" }}
              {% if d.scopus.sourcerecord_id %}
                <br>
                <a class="link-externo" target="_blank" rel="noopener"
                   href="https://www.scopus.com/sourceid/{{ d.scopus.sourcerecord_id }}#tabs=1">
                   Ver CiteScore/cuartil oficial en Scopus ↗
                </a>
                <small class="hint">(abre en tu navegador; el cuartil de la tabla de abajo es un estimado nuestro, no el oficial)</small>
              {% endif %}
            {% else %}
              No aparece en el Scopus Source List actual.
            {% endif %}

            <h4>Histórico SCImago (SJR / cuartil estimado / h-index / citas por doc.)</h4>
            {% if d.scimago and d.scimago.encontrada %}
              <table>
                <tr><th>Año</th><th>SJR</th><th>Cuartil*</th><th>h-index</th><th>Citas/doc</th></tr>
                {% for h in d.scimago.historia %}
                <tr>
                  <td>{{ h.anio }}</td>
                  <td>{{ "%.3f"|format(h.sjr) if h.sjr is not none else "-" }}</td>
                  <td>{{ "Q" ~ h.cuartil if h.cuartil is not none else "-" }}</td>
                  <td>{{ h.h_index if h.h_index is not none else "-" }}</td>
                  <td>{{ "%.2f"|format(h.avg_citations) if h.avg_citations is not none else "-" }}</td>
                </tr>
                {% endfor %}
              </table>
              <small class="hint">*Cuartil estimado por nosotros (ranking de SJR dentro de su categoría ASJC y año), no es el cuartil/CiteScore oficial de Scopus.</small>

              <div class="chart-wrap">
                <canvas id="chart-{{ r.issn|replace('-','_') }}" height="220"></canvas>
              </div>
              <script>
                (function() {
                  var historia = {{ d.scimago.historia|tojson }};
                  var ctx = document.getElementById("chart-{{ r.issn|replace('-','_') }}");
                  new Chart(ctx, {
                    type: "line",
                    data: {
                      labels: historia.map(function(h) { return h.anio; }),
                      datasets: [
                        {
                          label: "SJR",
                          data: historia.map(function(h) { return h.sjr; }),
                          borderColor: "#1f6feb",
                          backgroundColor: "#1f6feb",
                          yAxisID: "y_sjr",
                          spanGaps: true,
                        },
                        {
                          label: "Cuartil estimado",
                          data: historia.map(function(h) { return h.cuartil; }),
                          borderColor: "#bc4c00",
                          backgroundColor: "#bc4c00",
                          yAxisID: "y_cuartil",
                          spanGaps: true,
                        }
                      ]
                    },
                    options: {
                      responsive: true,
                      scales: {
                        y_sjr: { type: "linear", position: "left", title: { display: true, text: "SJR" } },
                        y_cuartil: {
                          type: "linear", position: "right", reverse: true, min: 1, max: 4,
                          ticks: { stepSize: 1, callback: function(v) { return "Q" + v; } },
                          title: { display: true, text: "Cuartil (mejor arriba)" },
                          grid: { drawOnChartArea: false }
                        }
                      }
                    }
                  });
                })();
              </script>
            {% else %}
              Sin datos en el dataset de SCImago.
            {% endif %}

            <h4>Volumen de artículos por año (Crossref)</h4>
            {% if d.volumen and d.volumen.consultada %}
              <table>
                <tr>
                  {% for h in d.volumen.historia %}
                  <th>{{ h.anio }}{{ "*" if h.anio == d.volumen.anio_actual_parcial else "" }}</th>
                  {% endfor %}
                </tr>
                <tr>
                  {% for h in d.volumen.historia %}
                  <td>{{ h.documentos if h.documentos is not none else "-" }}</td>
                  {% endfor %}
                </tr>
              </table>
              <small class="hint">*Año en curso, aún incompleto. Un salto brusco (ej. 2-3x el año anterior) es señal de posible pérdida de control de calidad editorial.</small>
            {% else %}
              No se pudo consultar volumen de artículos.
            {% endif %}

            <h4>Retractaciones (Crossref / Retraction Watch)</h4>
            {% if d.retractions and d.retractions.consultada %}
              {{ d.retractions.recientes|length }} en los últimos 24 meses
              ({{ d.retractions.total_historico }} en total histórico).
            {% else %}
              No se pudo consultar.
            {% endif %}
          </details>
          {% endif %}
        {% else %}
          <span class="badge" style="background:#8c959f">sin chequear</span>
        {% endif %}
      </td>
      <td>{{ r.fecha_chequeo or "-" }}</td>
      <td class="acciones">
        <form method="post" action="{{ url_for('revisar', issn=r.issn) }}">
          <button class="secundario" type="submit">Revisar ahora</button>
        </form>
        <form method="post" action="{{ url_for('eliminar', issn=r.issn) }}"
              onsubmit="return confirm('¿Quitar {{ r.nombre or r.issn }} de la watchlist?');">
          <button class="peligro" type="submit">Quitar</button>
        </form>
      </td>
    </tr>
    {% else %}
    <tr><td colspan="5"><small class="hint">Tu watchlist está vacía. Agrega una revista arriba.</small></td></tr>
    {% endfor %}
  </table>
</body>
</html>
"""


def _filas_watchlist():
    filas = []
    for r in load_watchlist():
        snap = last_snapshot(r["issn"])
        filas.append(
            {
                "nombre": r.get("nombre", ""),
                "issn": r["issn"],
                "score": snap["score"] if snap else None,
                "razones": snap["razones"] if snap else None,
                "fecha_chequeo": snap["fecha_chequeo"] if snap else None,
                "detalle": snap.get("detalle") if snap else None,
            }
        )
    return filas


@app.route("/")
def index():
    return render_template_string(PAGE, filas=_filas_watchlist(), colores=COLOR_POR_NIVEL)


@app.route("/agregar", methods=["POST"])
def agregar():
    issn = request.form.get("issn", "").strip()
    nombre = request.form.get("nombre", "").strip()
    if not issn:
        flash("Debes ingresar un ISSN.")
        return redirect(url_for("index"))

    add_journal(issn, nombre)
    resultado = evaluate_journal(issn, nombre)
    if not nombre:
        update_journal_nombre(issn, resultado["nombre"])
    save_snapshot(resultado)
    flash(f"'{resultado['nombre']}' agregada. Riesgo: {resultado['score']}.")
    return redirect(url_for("index"))


@app.route("/revisar/<issn>", methods=["POST"])
def revisar(issn):
    watchlist = {r["issn"]: r for r in load_watchlist()}
    nombre = watchlist.get(issn, {}).get("nombre", "")
    resultado = evaluate_journal(issn, nombre)
    save_snapshot(resultado)
    flash(f"'{resultado['nombre']}' actualizada. Riesgo: {resultado['score']}.")
    return redirect(url_for("index"))


@app.route("/eliminar/<issn>", methods=["POST"])
def eliminar(issn):
    remove_journal(issn)
    flash("Revista eliminada de la watchlist.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=False, port=5000)
