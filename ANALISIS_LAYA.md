# Análisis de la POC: Laya para triage de Jira

## Objetivo de esta POC

Queremos comprobar si un modelo de decisiones puede ayudar a clasificar tickets
de Jira según nuestra lógica de negocio. El ejemplo actual pregunta tres cosas:

1. ¿Qué equipo debería atender el ticket?
2. ¿Qué severidad tiene?
3. ¿Se crea un incidente o se agrega al backlog?

La POC no busca automatizar producción todavía. Busca hacer visible qué entiende
el modelo, dónde se equivoca y qué datos harían falta para adaptarlo.

## Qué es Laya

[Laya](https://huggingface.co/convaiinnovations/laya) es un modelo de decisiones
tipadas ("System 1"). En vez de generar una respuesta libre como un chat, recibe:

- Un **estado**: texto o JSON, por ejemplo un issue de Jira.
- Unas **preguntas tipadas**: por ejemplo una elección entre `product`,
  `payments` y `platform`.
- Los **criterios** que describen cada opción.

Y devuelve una opción por pregunta, más probabilidades y una señal de confianza.
Sirve cuando el programa necesita una decisión acotada que pueda consumir con
código: enrutar un ticket, priorizar una alerta, detectar si hace falta revisión
humana o seleccionar el siguiente paso de un flujo.

No sirve para explicar un problema en lenguaje natural, inventar una respuesta
para un usuario ni reemplazar políticas deterministas. La salida está limitada a
las opciones que le damos; no garantiza que la opción elegida sea verdadera.

## Qué hace este proyecto

El flujo es deliberadamente pequeño:

```text
Ticket de Jira + opciones de negocio
                |
                v
              Laya
                |
                v
Opción, probabilidad y confianza por cada decisión
                |
                v
Comparación con la respuesta esperada por negocio
```

`ticket_triage_poc.py` usa el endpoint local `/v1/systemone` y recorre un arreglo
de cinco tickets de ejemplo. Cada ticket contiene las decisiones esperadas, que
se usan sólo para comparar y nunca se mandan al modelo. Docker descarga el modelo
desde Hugging Face una vez y lo conserva en el volumen
`laya-model-cache`, por lo que reiniciar el servicio no vuelve a descargar los
pesos.

## Resultado observado

El ticket de prueba declara explícitamente que el botón está descentrado, el
checkout funciona y no hay usuarios bloqueados. La respuesta que esperamos es:

```text
owner_team = product
severity   = cosmetic
action     = add_to_backlog
```

En el ticket visual, Laya acertó el equipo (`product`), pero propuso `blocker`
y `create_incident`. La acción llegó a tener una confianza alta pese a ser
incorrecta para esta empresa.

La hipótesis más probable es que el checkpoint general todavía no representa
bien nuestra definición de "incidente", "cosmético" o "backlog". Esta POC no
prueba esa causa: sólo demuestra que el comportamiento actual no alcanza para
automatizar esas decisiones.

### Resultado actual de la POC

La última ejecución recorrió cinco tickets sintéticos: visual, pagos rechazados,
API caída, defecto funcional menor y ticket incompleto. Comparó 15 decisiones en
total contra las etiquetas esperadas:

| Decisión | Aciertos | Observación |
| --- | --- | --- |
| Equipo responsable | 2/5 | Confundió pagos y plataforma con `product` en algunos casos. |
| Severidad | 3/5 | Acertó los dos blockers claros, pero elevó un defecto menor y un ticket incompleto. |
| Primera acción | 2/5 | Tendió a proponer incidente incluso cuando debía ir a backlog o revisión. |
| **Total** | **7/15** | Resultado exploratorio; no es una métrica de producción. |
| Acción final por política | **5/5** | Usa hechos estructurados del ticket, no la propuesta de acción de Laya. |

Cinco casos sintéticos no alcanzan para medir precisión ni calibración. Sirven
para diseñar los casos de prueba y descubrir errores concretos antes de usar
tickets históricos anonimizados.

La confianza es una señal para investigar, no una autorización automática. En
esta misma POC una acción incorrecta tuvo confianza alta. Un umbral de confianza
debe elegirse únicamente después de medir resultados sobre un conjunto de
evaluación separado y etiquetado por negocio.

Como iteración, se probó cambiar el orden y el identificador de las opciones de
acción; Laya siguió proponiendo incidente para el ticket visual. También se probó
una pregunta binaria sobre si existía un incidente confirmado y marcó como
positivo tanto el ticket visual como el incompleto. Por eso la POC conserva la
propuesta cruda del modelo para evaluación, pero calcula la acción final con una
regla sobre hechos confirmados: flujo funcionando + nadie bloqueado va a backlog;
flujo detenido + usuarios bloqueados abre incidente; información faltante va a
revisión humana.

### Última iteración: separar propuesta y acción final

No se modificaron ni se reentrenaron los pesos de Laya. La iteración cambió el
rol que cumple el modelo dentro de la POC:

```text
Laya propone equipo, severidad y acción
                    |
                    v
La POC muestra y mide esa propuesta cruda
                    |
                    v
La política evalúa hechos confirmados del ticket
                    |
                    v
incidente / backlog / revisión humana
```

La política actual es intencionalmente pequeña y sólo usa dos campos:

- `checkout_works=true` y `users_blocked=false` → `add_to_backlog`.
- `checkout_works=false` y `users_blocked=true` → `create_incident`.
- Si alguno de esos hechos no es booleano confirmado → `needs_human_review`.

Con los cinco tickets de ejemplo, esta política acertó las cinco acciones
esperadas. Eso valida la regla sobre estos casos de prueba, **no** prueba que sea
una política completa para producción. En un Jira real habría que incorporar
otros hechos: pérdida o exposición de datos, impacto regional, alternativas
temporales, tipo de servicio y permisos para alertar a la guardia.

El script muestra esta diferencia con `✅ coincide` y `⚠️ no coincide`. No corrige
la respuesta del modelo: así podemos observar el problema antes de intentar
resolverlo.

## Taxonomía usada por la POC

Las opciones no son sólo nombres técnicos. Cada una se describe en el script con
inclusiones, exclusiones y ejemplos para reducir ambigüedad.

### Equipo responsable

| Respuesta | Elegir cuando | No elegir cuando |
| --- | --- | --- |
| `payments` | Falla autorizar/capturar pagos, cobro duplicado, reembolso, tarjeta o pasarela. | El checkout sólo tiene un defecto visual y cobrar sigue funcionando. |
| `platform` | Hay caída, error 5xx, latencia, despliegue, autenticación, base de datos, red o servicio compartido. | El fallo está aislado a una pantalla o regla de un producto. |
| `product` | Es un problema de interfaz, frontend, flujo o regla funcional de la aplicación. | La causa es infraestructura compartida o una transacción de pago fallida. |
| `needs_human_review` | Faltan datos para localizar la causa o hay más de un equipo posible. | Hay evidencia clara de uno de los equipos anteriores. |

### Severidad

| Respuesta | Elegir cuando | Ejemplo |
| --- | --- | --- |
| `blocker` | Impacto crítico confirmado en producción: función esencial detenida para muchos usuarios, datos expuestos/perdidos o pagos imposibles sin alternativa. | Nadie puede completar una compra. |
| `high` | Problema funcional importante y acotado, con una alternativa temporal. | Una región no puede descargar facturas, pero soporte puede enviarlas manualmente. |
| `low` | Defecto funcional menor, con poco alcance y alternativa; sin riesgo inmediato de dinero, datos o disponibilidad. | Un filtro no recuerda la última selección. |
| `cosmetic` | Sólo cambia apariencia o texto; el flujo funciona y no hay usuarios bloqueados. | Un botón está descentrado o tiene un color incorrecto. |
| `needs_human_review` | Se desconoce el entorno, alcance o impacto, o el ticket es contradictorio. | "No funciona" sin indicar qué, para quién ni dónde. |

### Primera acción

| Respuesta | Elegir cuando | No elegir cuando |
| --- | --- | --- |
| `create_incident` | Hay un `blocker` confirmado en producción que exige coordinación inmediata: caída crítica, bloqueo masivo, pagos imposibles sin alternativa o riesgo de datos. | Es visual, tiene alternativa o todavía no se confirmó el alcance. |
| `add_to_backlog` | Es una mejora o defecto conocido de severidad `cosmetic`, `low` o `high`, sin necesidad de respuesta inmediata de incidentes. | La función crítica está detenida o hay daño urgente confirmado. |
| `needs_human_review` | Faltan hechos críticos o hay indicios de riesgo que no alcanzan para confirmar un blocker. | El ticket ya aporta alcance, impacto y alternativa de forma clara. |

La ejecución posterior a ampliar los criterios acertó `owner_team=product` y
`severity=cosmetic`, pero aún eligió `action=create_incident`. Es precisamente el
tipo de error que debemos medir con una colección de tickets reales antes de
automatizar o de decidir el alcance del fine-tuning.

Las tres preguntas se responden en la misma llamada, pero son decisiones
independientes del modelo. Por eso `severity=cosmetic` y
`action=create_incident` pueden aparecer juntas, aunque se contradigan desde el
punto de vista del negocio. Para producción, la acción no debería depender sólo
de la respuesta `action` de Laya: el código debe combinar hechos confirmados del
ticket. Por ejemplo:

```text
si faltan alcance o impacto          -> revisión humana
si hay blocker confirmado            -> crear incidente
si es cosmetic, low o high conocido  -> backlog
```

La implementación actual muestra ambas salidas: la propuesta de Laya y la acción
final de la política. Esto permite mejorar o entrenar el modelo sin delegarle una
acción operativa de alto impacto.

## Conclusiones actuales

1. Laya sirve para expresar y devolver decisiones cerradas, pero en esta POC no
   tiene precisión suficiente para decidir automáticamente equipo, severidad o
   acción de Jira.
2. Las descripciones detalladas de las categorías ayudaron en algunos casos,
   pero no resolvieron la tendencia a escalar acciones a incidente.
3. La salida tipada y la confianza no reemplazan reglas de negocio. Una respuesta
   de alta confianza puede ser errónea para un dominio que el modelo no conoce.
4. Separar la propuesta del modelo de la acción final permite explorar Laya sin
   activar incidentes incorrectos.
5. El siguiente avance para mejorar a Laya —no sólo proteger el flujo— es crear
   un conjunto de tickets históricos anonimizados, etiquetados y separado entre
   entrenamiento y evaluación. Ese conjunto permitirá decidir si el fine-tuning
   mejora los errores que vemos en esta POC.

## Qué haríamos en una implementación real

Las tres capas deberían estar separadas:

| Capa | Responsabilidad | Ejemplo |
| --- | --- | --- |
| Reglas de negocio | Hechos no negociables | Un ticket sin usuarios bloqueados no abre guardia. |
| Laya | Juicios ambiguos | Decidir si una descripción pertenece a `product` o `platform`. |
| Persona | Casos dudosos o de alto impacto | Validar una posible incidencia de pagos. |

Primero conviene aplicar reglas simples cuando los campos estructurados del ticket
ya contienen la respuesta. Después se usa el modelo para los casos donde una regla
no alcanza. Las decisiones irreversibles o costosas no deben depender solamente
de una predicción del modelo.

## Fine-tuning para la lógica del negocio

Sí, es posible ajustar Laya. La tarjeta del modelo incluye la opción de
[fine-tuning para mejorar precisión](https://huggingface.co/convaiinnovations/laya).
El objetivo sería que aprenda las categorías y precedencias reales de este Jira,
no solamente las categorías que conoció durante su entrenamiento general.

El plan sería:

1. Exportar tickets históricos representativos, sin secretos ni datos personales
   innecesarios.
2. Etiquetar cada ticket con las respuestas correctas de negocio. Por ejemplo:
   `owner_team=product`, `severity=cosmetic`, `action=add_to_backlog`.
3. Separar un conjunto de evaluación que **no** se use para entrenar.
4. Ajustar el modelo con el conjunto de entrenamiento.
5. Medir precisión por decisión y por clase en el conjunto separado. También
   medir cuántos falsos incidentes produce, porque ese error es costoso.
6. Elegir umbrales de revisión humana con esas mediciones, midiendo los falsos
   incidentes por separado, y desplegar de forma gradual.

Antes de entrenar, una alternativa más barata es mejorar los campos del ticket y
los criterios de las opciones. Si aun con tickets claros el resultado sigue
fallando, como ocurre en este ejemplo, los datos etiquetados son la evidencia
necesaria para decidir si el fine-tuning vale la pena.

## Qué es Jev

[Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) es el
primer modelo público "System One" de TypeSafe. Su propuesta es parecida a la de
Laya: estado no estructurado o estructurado de entrada, preguntas tipadas y
decisiones probabilísticas de salida. TypeSafe lo plantea para clasificación,
enrutamiento, puntajes, validaciones y ramas de un flujo de software.

Jev ofrece tres primitivas principales a través de su API:

- `Choice`: elegir una opción de un conjunto definido.
- `Score`: asignar un nivel sobre una escala ordenada.
- `Noul`: responder una pregunta sí/no con una probabilidad.

Su API y modelos se consultan como un servicio hospedado con credenciales, según
su [documentación de la API](https://api.typesafe.ai/docs). Al momento de este
análisis, TypeSafe presenta Jev como acceso temprano. No es el modelo local que
este Docker descarga desde Hugging Face.

## Laya y Jev: comparación útil para esta POC

| Aspecto | Laya | Jev |
| --- | --- | --- |
| Uso principal | Decisiones tipadas sobre un estado. | Decisiones tipadas sobre un estado. |
| Integración actual | Modelo local, servido por nuestro Docker. | API hospedada de TypeSafe. |
| Resultado esperado | Opción, probabilidades y confianza. | Opción/puntaje/sí-no, probabilidades y confianza según el tipo. |
| Regla de negocio | Debe vivir en nuestro código y datos. | Debe vivir en nuestro código y datos. |
| Garantía del formato | No genera una respuesta libre fuera de las opciones. | Salida tipada para que el software la consuma. |
| Garantía de acierto | No la da; debe evaluarse con datos propios. | No la da; debe evaluarse con datos propios. |

La diferencia práctica inicial no es "cuál decide mágicamente mejor". Para
saberlo habría que usar el mismo conjunto de tickets etiquetados, medir la misma
métrica y comparar errores. Para esta POC, Laya ya permite aprender el patrón sin
enviar tickets a otro proveedor y sin depender de otra API.

## Próximo experimento recomendado

Crear un archivo pequeño de evaluación con tickets reales anonimizados y sus
respuestas esperadas. Ejecutar Laya sobre todos ellos y calcular, por separado,
el acierto de equipo, severidad y acción. Con esa evidencia decidimos entre:

- mejorar los criterios o el contenido del ticket;
- conservar sólo un uso de bajo riesgo, como sugerir el equipo responsable;
- entrenar un checkpoint adaptado al negocio;
- comparar el mismo conjunto contra Jev antes de elegir un proveedor.
