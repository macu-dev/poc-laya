# POC Laya: triage de issues Jira

Esta POC permite entender qué resuelve Laya: recibe un estado (por ejemplo, un
issue de Jira) y el conjunto cerrado de decisiones posibles. Devuelve una opción
por cada decisión, con probabilidad y confianza. No genera texto ni aplica reglas
de negocio por sí mismo.

El ejemplo recorre un arreglo `tickets` con cinco issues de Jira y consulta tres
propuestas de Laya para cada uno:

- Qué equipo debe resolverlo.
- Qué severidad tiene.
- Qué acción propone: incidente, backlog o revisión.

Cada respuesta está descrita con casos que incluye, casos que excluye y ejemplos.
Además existe `needs_human_review` en las tres decisiones: un ticket incompleto
no debería forzar una clasificación inventada. Cada ticket tiene
`expected_choices`, pero esas respuestas esperadas sólo sirven para medir el
resultado; nunca se envían al modelo.

La POC separa dos responsabilidades:

```text
Laya propone equipo, severidad y acción
                |
                v
La POC compara la propuesta con la respuesta esperada
                |
                v
Una regla de negocio calcula la acción final usando hechos confirmados
```

El ejemplo está en [`ticket_triage_poc.py`](ticket_triage_poc.py). No usa dependencias Python adicionales: habla con el servidor Laya por HTTP.

Para el objetivo, límites observados, fine-tuning y comparación con Jev, leé
[`ANALISIS_LAYA.md`](ANALISIS_LAYA.md).

## 1. Configurar el token

Creá el archivo local de variables y agregá un token de lectura de Hugging Face. El archivo `.env` no se incluye en Git ni dentro de la imagen Docker.

```bash
cp .env.example .env
# Editá .env y reemplazá HF_TOKEN por tu token hf_...
```

## 2. Iniciar Laya

```bash
docker-compose up --build
```

La primera ejecución descarga el modelo de Hugging Face al volumen Docker `laya-model-cache`. Las ejecuciones siguientes reutilizan la caché y no descargan los pesos otra vez.

## 3. Ejecutar el ejemplo Jira

Con el servidor iniciado, en otra terminal ejecutá:

```bash
docker-compose exec laya python /app/ticket_triage_poc.py
```

La salida muestra la propuesta cruda de Laya, la compara con la respuesta esperada
por negocio y termina con un resumen de aciertos. La acción final (`incidente`,
`backlog` o `revisión`) no depende solamente de la propuesta del modelo: se deriva
de hechos estructurados del ticket.

```text
Evaluando 5 tickets de Jira

Tarea evaluada:
WEB-123 — Botón de comprar descentrado
Impacto: El impacto es sólo visual; no afecta checkout ni pagos.

Respuesta de Laya:
- owner_team: product
  Probabilidad: ... | Confianza: ... | ✅ coincide
- severity: cosmetic
  Probabilidad: ... | Confianza: ... | ✅ coincide
- action: create_incident
  Probabilidad: ... | Confianza: ... | ⚠️ no coincide; se esperaba add_to_backlog

Acción final según política de negocio:
- action: add_to_backlog
  El flujo funciona y no hay usuarios bloqueados. | ✅ coincide

Resumen de Laya: 7/15 decisiones coinciden con la lógica esperada.
Resumen de la política de acción: 5/5 acciones coinciden con la lógica esperada.
```

Los porcentajes pueden variar entre ejecuciones. Los resultados `7/15` y `5/5`
corresponden a los cinco tickets sintéticos incluidos; no son una métrica de
producción. La POC no corrige la propuesta de Laya: la comparación existe para
mostrar dónde falla la lógica del modelo.

### Política de acción de esta POC

La política es pequeña y explícita. Usa los campos `checkout_works` y
`users_blocked`:

- Si checkout funciona y nadie está bloqueado: `add_to_backlog`.
- Si checkout no funciona y hay usuarios bloqueados: `create_incident`.
- Si falta uno de esos hechos: `needs_human_review`.

Esta regla evita que una predicción incorrecta abra un incidente. No es todavía
una política completa de producción: faltaría considerar seguridad, pérdida de
datos, alcance regional, alternativas temporales y permisos de guardia.

## ¿Qué haríamos para usarlo en el negocio?

1. Exportar tickets históricos y etiquetar la decisión correcta para cada uno.
2. Mantener un conjunto de prueba separado: sirve para medir si el modelo mejora,
   no para entrenarlo.
3. Ajustar (fine-tune) Laya con los tickets etiquetados y evaluar ese conjunto de
   prueba. Laya está diseñado para decisiones tipadas y su documentación contempla
   fine-tuning; el checkpoint actual ya fue ajustado para otros dominios, no para
   las reglas de este Jira.
4. Ajustar umbrales y automatizar sólo las decisiones que alcancen la precisión
   acordada con negocio; las demás se envían a revisión humana.

## Cambiar el issue sin reiniciar

Agregá o editá objetos dentro del arreglo `tickets` de [`ticket_triage_poc.py`](ticket_triage_poc.py) y volvés a ejecutar el mismo comando. Cada objeto tiene `issue` y `expected_choices`; estas últimas no se envían al modelo, sólo sirven para comparar. Conservá, en particular, `affected_users` y `business_impact`: son los datos que diferencian un defecto visual de un incidente.

```bash
docker-compose exec laya python /app/ticket_triage_poc.py
```

El archivo se monta desde tu carpeta local al contenedor, por eso no hace falta reconstruir la imagen ni reiniciar Laya.

## Ejecutar automáticamente al guardar

Iniciá Laya en segundo plano:

```bash
docker-compose up -d laya
```

Después iniciá el watcher:

```bash
docker-compose --profile watch run --rm --no-deps watch
```

Primero imprime la decisión actual. Luego, cada vez que guardás `ticket_triage_poc.py`, vuelve a ejecutar el triage automáticamente. Detenelo con `Ctrl+C`; Laya sigue en ejecución. El watcher usa un contenedor Python temporal, por lo que no requiere reconstruir la imagen de Laya.

## Borrar la caché del modelo

Este comando borra los pesos descargados. La próxima vez se descargarán otra vez:

```bash
docker-compose down --volumes
```
