"""POC mínima: comparar decisiones de Laya con la lógica de negocio."""

import json
import os
from urllib.request import Request, urlopen

# Cada objeto representa un ticket y la decisión esperada por negocio.
# expected_choices se usa sólo para comparar el resultado: no se envía a Laya.
tickets = [
    {
        "issue": {
            "key": "WEB-123",
            "type": "Bug",
            "component": "frontend",
            "summary": "Botón de comprar descentrado",
            "description": "El botón de comprar no está centrado en la página de inicio.",
            "environment": "production",
            "checkout_works": True,
            "users_blocked": False,
            "affected_users": "No bloquea a ningún usuario: la compra funciona.",
            "business_impact": "El impacto es sólo visual; no afecta checkout ni pagos.",
        },
        "expected_choices": {
            "owner_team": "product",
            "severity": "cosmetic",
            "action": "add_to_backlog",
        },
    },
    {
        "issue": {
            "key": "PAY-417",
            "type": "Bug",
            "component": "checkout",
            "summary": "Pagos con tarjeta rechazados",
            "description": "La pasarela rechaza todos los pagos con tarjeta desde hace 15 minutos.",
            "environment": "production",
            "checkout_works": False,
            "users_blocked": True,
            "affected_users": "Todos los clientes que intentan pagar con tarjeta están bloqueados.",
            "business_impact": "No se pueden completar ventas con el medio de pago principal.",
        },
        "expected_choices": {
            "owner_team": "payments",
            "severity": "blocker",
            "action": "create_incident",
        },
    },
    {
        "issue": {
            "key": "PLAT-88",
            "type": "Incident",
            "component": "api",
            "summary": "API responde 503",
            "description": "La API pública responde HTTP 503 para todas las rutas desde el último despliegue.",
            "environment": "production",
            "checkout_works": False,
            "users_blocked": True,
            "affected_users": "Todos los usuarios de web y móvil no pueden usar la aplicación.",
            "business_impact": "La aplicación no está disponible para todos los clientes.",
        },
        "expected_choices": {
            "owner_team": "platform",
            "severity": "blocker",
            "action": "create_incident",
        },
    },
    {
        "issue": {
            "key": "PROD-202",
            "type": "Bug",
            "component": "search",
            "summary": "El filtro de productos no conserva la selección",
            "description": "Al volver al catálogo se pierde el filtro elegido, pero se puede volver a seleccionar.",
            "environment": "production",
            "checkout_works": True,
            "users_blocked": False,
            "affected_users": "Afecta a usuarios que navegan el catálogo; pueden continuar manualmente.",
            "business_impact": "Molestia de usabilidad sin impedir compras ni afectar datos.",
        },
        "expected_choices": {
            "owner_team": "product",
            "severity": "low",
            "action": "add_to_backlog",
        },
    },
    {
        "issue": {
            "key": "JIRA-UNKNOWN",
            "type": "Bug",
            "component": "unknown",
            "summary": "No funciona",
            "description": "Un usuario informa que no funciona desde ayer.",
            "environment": "unknown",
            "checkout_works": "unknown",
            "users_blocked": "unknown",
            "affected_users": "No informado.",
            "business_impact": "No informado.",
        },
        "expected_choices": {
            "owner_team": "needs_human_review",
            "severity": "needs_human_review",
            "action": "needs_human_review",
        },
    },
]
# Cada criterio es una definición de negocio: incluye casos, exclusiones y ejemplos.
# Así Laya no depende sólo del nombre corto de la opción.
questions = {
    "owner_team": {
        "type": "choice",
        "instructions": (
            "Elegí el equipo que debe resolver la causa principal del issue. "
            "Usá solamente los hechos del ticket; si no alcanza la información, elegí needs_human_review."
        ),
        "criteria": {
            "payments": (
                "Equipo Payments. Incluye fallas al autorizar o capturar pagos, cobros duplicados, "
                "reembolsos incorrectos, tarjetas rechazadas y errores de la pasarela. "
                "Ejemplo: 'el pago con Visa es rechazado'. Excluye un problema visual del checkout "
                "cuando cobrar y comprar siguen funcionando."
            ),
            "platform": (
                "Equipo Platform. Incluye caídas, errores 5xx, latencia, despliegues, autenticación, "
                "bases de datos, redes o servicios compartidos que afectan a varias funciones. "
                "Ejemplo: 'la API responde 503 para todos los usuarios'. Excluye un bug aislado de "
                "una pantalla o una regla propia de un producto."
            ),
            "product": (
                "Equipo Product. Incluye interfaz, frontend, flujos y reglas funcionales de la aplicación. "
                "Ejemplo: botón descentrado, filtro que no aplica o pantalla que muestra información errónea. "
                "Excluye una falla de infraestructura compartida y una transacción de pago fallida."
            ),
            "needs_human_review": (
                "Revisión humana. Elegir sólo si el ticket no indica qué parte falla o si podría pertenecer "
                "a más de un equipo y faltan datos para distinguirlo."
            ),
        },
    },
    "severity": {
        "type": "choice",
        "instructions": (
            "Elegí la severidad según usuarios bloqueados, alcance, entorno e impacto de negocio. "
            "No subas la severidad por el tono del texto. Si faltan esos datos, elegí needs_human_review."
        ),
        "criteria": {
            "blocker": (
                "Incidente crítico confirmado en producción: todos o una parte importante de usuarios no pueden "
                "usar una función esencial, hay pérdida o exposición de datos, o no se puede cobrar y no existe "
                "alternativa. Requiere atención inmediata. Ejemplo: 'ningún usuario puede completar una compra'."
            ),
            "high": (
                "Problema funcional importante en producción, con impacto relevante pero acotado: afecta a un grupo "
                "de usuarios o una función importante y existe una alternativa temporal. Ejemplo: 'clientes de una "
                "región no pueden descargar facturas, pero soporte puede enviarlas manualmente'."
            ),
            "low": (
                "Defecto funcional menor: el flujo tiene un error, pero pocos usuarios están afectados, hay alternativa "
                "y no hay riesgo inmediato de dinero, datos o disponibilidad. Ejemplo: 'un filtro no recuerda la última "
                "selección'. Excluye defectos sólo visuales."
            ),
            "cosmetic": (
                "Defecto visual o de texto únicamente: alineación, color, tipografía, espaciado, icono o copy. "
                "La función funciona y nadie está bloqueado. Ejemplo: 'el botón de comprar está descentrado'."
            ),
            "needs_human_review": (
                "Revisión humana. Elegir si no se conoce el entorno, los usuarios afectados o el impacto, o si el ticket "
                "da información contradictoria."
            ),
        },
    },
    "action": {
        "type": "choice",
        "instructions": (
            "Elegí la primera acción operativa. Un incidente sólo corresponde a un blocker confirmado; "
            "un ticket incompleto debe ir a revisión humana."
        ),
        "criteria": {
            "create_incident": (
                "Crear incidente y avisar a la guardia ahora. Usar sólo ante un blocker confirmado en producción: "
                "función crítica detenida, usuarios bloqueados a gran escala, pérdida o exposición de datos, o pagos "
                "imposibles sin alternativa."
            ),
            "add_to_backlog": (
                "Crear o actualizar un ítem de backlog. Usar para mejoras, defectos cosméticos y problemas de severidad "
                "low o high que ya tienen alcance conocido y no requieren coordinación inmediata de incidentes."
            ),
            "needs_human_review": (
                "Pedir revisión humana antes de actuar. Usar si faltan hechos críticos —entorno, alcance, usuarios "
                "afectados o alternativa— o si hay señales de riesgo pero no se puede confirmar un blocker."
            ),
        },
    },
}

def ask_laya(issue):
    payload = {
        "state": {"source": "Jira", "issue": issue},
        "model": "multilingual",
        "questions": questions,
    }
    request = Request(
        f"{os.getenv('LAYA_URL', 'http://localhost:8000')}/v1/systemone",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request) as response:
        return json.load(response)["answers"]


def decide_final_action(issue):
    """Aplica una política simple sobre hechos confirmados, no sobre texto ambiguo."""
    checkout_works = issue.get("checkout_works")
    users_blocked = issue.get("users_blocked")

    if not isinstance(checkout_works, bool) or not isinstance(users_blocked, bool):
        return "needs_human_review", "Faltan hechos confirmados sobre el flujo y los usuarios afectados."
    if checkout_works and not users_blocked:
        return "add_to_backlog", "El flujo funciona y no hay usuarios bloqueados."
    if not checkout_works and users_blocked:
        return "create_incident", "El flujo está detenido y hay usuarios bloqueados."
    return "needs_human_review", "Los hechos no alcanzan para decidir entre incidente y backlog."


print(f"Evaluando {len(tickets)} tickets de Jira")
laya_matches = 0
total_decisions = 0
policy_action_matches = 0
for ticket in tickets:
    issue = ticket["issue"]
    expected_choices = ticket["expected_choices"]
    decisions = ask_laya(issue)

    print("\n" + "=" * 72)
    print("Tarea evaluada:")
    print(f"{issue['key']} — {issue['summary']}")
    print(f"Impacto: {issue['business_impact']}")
    print("\nRespuesta de Laya:")
    for name, answer in decisions.items():
        choice = answer["choice"]
        explanation = questions[name]["criteria"][choice]
        probability = answer["answer_confidence"]
        confidence = answer.get("confidence")
        confidence_text = f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "no disponible"
        expected = expected_choices[name]
        verdict = "✅ coincide" if choice == expected else f"⚠️ no coincide; se esperaba {expected}"
        laya_matches += choice == expected
        total_decisions += 1

        print(f"- {name}: {choice}")
        print(f"  {explanation}")
        print(f"  Probabilidad: {probability:.0%} | Confianza: {confidence_text} | {verdict}")

    final_action, policy_reason = decide_final_action(issue)
    expected_action = expected_choices["action"]
    policy_verdict = "✅ coincide" if final_action == expected_action else f"⚠️ no coincide; se esperaba {expected_action}"
    policy_action_matches += final_action == expected_action
    print("\nAcción final según política de negocio:")
    print(f"- action: {final_action}")
    print(f"  {policy_reason} | {policy_verdict}")

print("\n" + "=" * 72)
print(f"Resumen de Laya: {laya_matches}/{total_decisions} decisiones coinciden con la lógica esperada.")
print(f"Resumen de la política de acción: {policy_action_matches}/{len(tickets)} acciones coinciden con la lógica esperada.")
