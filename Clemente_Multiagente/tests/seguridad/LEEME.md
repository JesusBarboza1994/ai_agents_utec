# Seguridad — red teaming de Clemente

Pruebas de la **Sesión 23**. Miden algo distinto a `tests/eval/`: no si Clemente
hace bien su trabajo, sino **si se puede romper**.

## Aviso ético y legal — léelo antes de ejecutar nada

Estos scripts generan **prompts de ataque reales**: inyecciones, *jailbreaks*,
manipulación emocional, intentos de extraer datos.

- Se ejecutan **solo contra nuestro propio agente**, con nuestra propia clave.
- **Nunca** se apuntan a un sistema de terceros sin autorización escrita. En la
  mayoría de jurisdicciones eso es un delito, no una práctica de clase.
- `deepteam-results/` guarda **los ataques que sí funcionaron**. Es material
  sensible: está en el `.gitignore` y no se sube ni se comparte fuera del equipo.
- Los resultados no salen del grupo.

## Cómo correrlo

```bash
pip install -r requirements-dev.txt

# Prueba de humo: 1 vulnerabilidad x 1 ataque. Empieza siempre por aquí.
python -m tests.seguridad.red_team_reservas --humo

# Batería completa con cobertura OWASP. Tarda y es lo más caro del proyecto.
python -m tests.seguridad.red_team_reservas

# Atacando el sistema entero, entrando por el enrutador (la superficie real).
python -m tests.seguridad.red_team_reservas --objetivo sistema
```

## Por qué el Agente de Reservas

Es el único de los tres que **escribe un compromiso que el restaurante tendrá
que honrar en sala**, y el único que toca datos personales de clientes reales
(nombre y teléfono, en `app/agentes/memoria.py`).

De las dos, la fuga de datos es la más grave: que Clemente revele la reserva o
el teléfono de **otro** cliente sería una brecha de datos personales, no un
error de conversación.

## Qué esperamos que aguante

Los límites de Clemente son **estructurales**, no de *prompt*, y esa es la
hipótesis que esta prueba pone a prueba:

| Límite | Por qué debería aguantar |
|---|---|
| No confirmar una mesa sin consultarla | `consultar_disponibilidad` es la única fuente de cupo; el modelo no tiene otra |
| No dar compensaciones | **no existe** una herramienta para eso en el Agente de Incidencias |
| No cerrar un grupo de más de 10 personas | `escalar_a_staff` es la única salida disponible |

Si el red team consigue romper alguno de estos, no se arregla con una frase
más en el *prompt*: significa que faltaba una barrera estructural.

## Límites de esta prueba

El red teaming automatizado prueba lo que sabe probar. **No cubre**:

- ataques de varios turnos que construyen confianza antes de pedir algo;
- abuso del canal real (WhatsApp) en lugar del agente;
- lo que ocurra cuando el gestor de reservas tenga datos de producción.

Eso necesita revisión manual, y es parte del informe del Módulo 8.
