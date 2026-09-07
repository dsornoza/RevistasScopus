"""Combina las señales de las distintas fuentes en un score de riesgo."""
import datetime

NIVELES = ["Bajo", "Medio", "Medio-alto", "Alto"]


def _peso(nivel: str) -> int:
    return NIVELES.index(nivel)


def compute_score(scopus_info: dict, scimago_info: dict, retractions_info: dict, volumen_info: dict | None = None) -> dict:
    razones = []
    nivel = "Bajo"

    # --- Señal directa: estado oficial en Scopus ---
    if scopus_info.get("encontrada"):
        estado = str(scopus_info.get("estado") or "").strip().lower()
        if estado and "inactive" in estado:
            nivel = "Alto"
            razones.append(
                f"La revista figura como '{scopus_info.get('estado')}' en el Scopus Source List oficial "
                "(fuente de verdad final)."
            )
    else:
        nivel = "Alto"
        razones.append(
            f"El ISSN no aparece en el Scopus Source List actual: {scopus_info.get('motivo', '')}"
        )

    # --- Señales de SCImago ---
    if scimago_info.get("encontrada"):
        toda_la_historia = scimago_info["historia"]

        # Señal directa: el propio dataset ya etiqueta el título como discontinuado.
        if scimago_info.get("marcado_discontinued"):
            nivel = "Alto"
            razones.append(
                "El dataset de SCImago ya etiqueta esta revista como '(discontinued)'."
            )

        # Caída de SJR interanual (entre los dos últimos años con dato).
        con_sjr = [h for h in toda_la_historia if h["sjr"] is not None]
        if len(con_sjr) >= 2:
            ultimo, penultimo = con_sjr[-1], con_sjr[-2]
            if penultimo["sjr"] > 0:
                variacion = (ultimo["sjr"] - penultimo["sjr"]) / penultimo["sjr"]
                if variacion <= -0.3:
                    if _peso("Medio-alto") > _peso(nivel):
                        nivel = "Medio-alto"
                    razones.append(
                        f"El SJR cayó {abs(variacion) * 100:.0f}% entre {penultimo['anio']} "
                        f"({penultimo['sjr']:.3f}) y {ultimo['anio']} ({ultimo['sjr']:.3f})."
                    )

        # Caída de cuartil interanual (entre los dos últimos años con dato).
        con_cuartil = [h for h in toda_la_historia if h["cuartil"] is not None]
        if len(con_cuartil) >= 2:
            ultimo_c, penultimo_c = con_cuartil[-1], con_cuartil[-2]
            salto = ultimo_c["cuartil"] - penultimo_c["cuartil"]  # positivo = empeoró
            if salto >= 2:
                if _peso("Medio-alto") > _peso(nivel):
                    nivel = "Medio-alto"
                razones.append(
                    f"El cuartil empeoró de Q{penultimo_c['cuartil']} ({penultimo_c['anio']}) "
                    f"a Q{ultimo_c['cuartil']} ({ultimo_c['anio']})."
                )
            elif salto == 1:
                if _peso("Medio") > _peso(nivel):
                    nivel = "Medio"
                razones.append(
                    f"El cuartil bajó de Q{penultimo_c['cuartil']} ({penultimo_c['anio']}) "
                    f"a Q{ultimo_c['cuartil']} ({ultimo_c['anio']})."
                )

        # SJR faltante en el año más reciente, habiendo existido el año anterior:
        # suele pasar cuando la revista ya está en revisión/proceso de exclusión.
        if len(toda_la_historia) >= 2:
            ultimo_reg = toda_la_historia[-1]
            penultimo_reg = toda_la_historia[-2]
            if ultimo_reg["sjr"] is None and penultimo_reg["sjr"] is not None:
                if _peso("Medio-alto") > _peso(nivel):
                    nivel = "Medio-alto"
                razones.append(
                    f"SCImago no calculó SJR para {ultimo_reg['anio']} pese a que sí lo hizo en "
                    f"{penultimo_reg['anio']} ({penultimo_reg['sjr']:.3f}); frecuente en revistas "
                    "en proceso de revisión/exclusión."
                )

        # Declive sostenido de citas por documento (2+ caídas consecutivas en los últimos 3 años).
        con_citas = [h for h in toda_la_historia if h["avg_citations"] is not None][-3:]
        if len(con_citas) == 3 and con_citas[0]["avg_citations"] > con_citas[1]["avg_citations"] > con_citas[2]["avg_citations"]:
            if _peso("Medio") > _peso(nivel):
                nivel = "Medio"
            razones.append(
                "Las citas promedio por documento cayeron de forma sostenida en los últimos "
                f"3 años ({con_citas[0]['avg_citations']:.2f} → {con_citas[1]['avg_citations']:.2f} → "
                f"{con_citas[2]['avg_citations']:.2f})."
            )

        ultimo_anio = toda_la_historia[-1]["anio"] if toda_la_historia else None
        if ultimo_anio and datetime.date.today().year - ultimo_anio >= 2:
            razones.append(
                f"El dataset de SCImago no tiene datos más recientes que {ultimo_anio}; "
                "puede haber cambios posteriores no capturados. Revisar manualmente scimagojr.com."
            )
    else:
        razones.append(
            f"Sin datos históricos de SCImago: {scimago_info.get('motivo', '')}"
        )

    # --- Señal: retractaciones recientes ---
    if retractions_info.get("consultada"):
        recientes = retractions_info.get("recientes", [])
        if len(recientes) >= 2:
            if _peso("Medio-alto") > _peso(nivel):
                nivel = "Medio-alto"
            razones.append(f"{len(recientes)} retractaciones registradas en los últimos 24 meses.")
        elif len(recientes) == 1:
            if _peso("Medio") > _peso(nivel):
                nivel = "Medio"
            razones.append("1 retractación registrada en los últimos 24 meses.")
    else:
        razones.append(f"No se pudo consultar Crossref/Retraction Watch: {retractions_info.get('motivo', '')}")

    # --- Señal: explosión de volumen de artículos/año (Crossref) ---
    # Salto brusco de documentos publicados por año: patrón documentado en revistas
    # que bajan su control de calidad mientras están bajo revisión CSAB de Scopus
    # (ej. una revista que pasa de 4 a 16 issues/año, o de ~5 a ~2000 artículos/año).
    if volumen_info and volumen_info.get("consultada"):
        anio_parcial = volumen_info.get("anio_actual_parcial")
        con_datos = [h for h in volumen_info["historia"] if h["documentos"] is not None]
        anios_completos = [h for h in con_datos if h["anio"] != anio_parcial]
        parcial = next((h for h in con_datos if h["anio"] == anio_parcial), None)

        # Comparación entre los dos últimos años COMPLETOS (el año en curso se trata aparte,
        # porque compararlo directo contra un año completo puede parecer una caída falsa).
        if len(anios_completos) >= 2:
            ultimo_v, penultimo_v = anios_completos[-1], anios_completos[-2]
            if penultimo_v["documentos"] >= 5:
                ratio = ultimo_v["documentos"] / penultimo_v["documentos"]
                if ratio >= 3:
                    nivel = "Alto"
                    razones.append(
                        f"Explosión de volumen: de {penultimo_v['documentos']} artículos en {penultimo_v['anio']} "
                        f"a {ultimo_v['documentos']} en {ultimo_v['anio']}; típico de revistas que bajan su "
                        "control de calidad bajo revisión CSAB de Scopus."
                    )
                elif ratio >= 1.5:
                    if _peso("Medio-alto") > _peso(nivel):
                        nivel = "Medio-alto"
                    razones.append(
                        f"Crecimiento fuerte de volumen: de {penultimo_v['documentos']} artículos en "
                        f"{penultimo_v['anio']} a {ultimo_v['documentos']} en {ultimo_v['anio']}."
                    )

        # El año en curso (incompleto) ya iguala o supera un año completo anterior:
        # señal fuerte, porque todavía le quedan meses por sumar.
        if parcial and anios_completos and parcial["documentos"] is not None:
            referencia = anios_completos[-1]
            if referencia["documentos"] >= 5 and parcial["documentos"] >= referencia["documentos"]:
                nivel = "Alto"
                razones.append(
                    f"El año en curso ({parcial['anio']}, aún incompleto) ya lleva {parcial['documentos']} "
                    f"artículos, superando los {referencia['documentos']} de todo {referencia['anio']} — "
                    "con meses todavía por delante."
                )
    else:
        razones.append(
            f"No se pudo consultar el volumen de artículos por año en Crossref: "
            f"{(volumen_info or {}).get('motivo', '')}"
        )

    if not razones or (len(razones) == 1 and nivel == "Bajo"):
        razones.append("No se detectaron señales de riesgo en las fuentes consultadas.")

    return {"nivel": nivel, "razones": razones}
