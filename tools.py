tools = [
  {
    "name": 'get_current_datetime',
    "description":
      'Obtiene la fecha y hora actual. Úsala siempre antes de interpretar, validar o confirmar cualquier referencia temporal del cliente.',
    "parameters": {
      "type": "object",
      "required": [],
      "properties": {},
      "additionalProperties": False,
    },
    "type": "function",
  },
  {
    "name": 'check_availability',
    "description":
      'Consulta disponibilidad en el restaurante para una fecha, hora, cantidad de personas y zona determinada. Debe ejecutarse antes de crear la reserva si el cliente pregunta por disponibilidad.',
    "parameters": {
      "type": "object",
      "required": ['date', 'hour', 'peopleQuantity'],
      "properties": {
        "date": 'Fecha en formato YYYY-MM-DD',
        "hour": 'Hora en formato HH:MM',
        "peopleQuantity": 'Cantidad de personas',
        "zone": 'Nombre de la zona a consultar (opcional)',
      },
      "additionalProperties": False,
    },
    type: 'function',
  },
  {
    "name": 'create_reservation_request',
    "description":
      'Crea una solicitud de reserva en el restaurante. Solo ejecutar tras recibir confirmación explícita del cliente (CONFIRMO o SI). Devuelve un código/correlativo que debe incluirse en la respuesta al cliente.',
    "parameters": {
      "type": "object",
      "required": ['date', 'hour', 'weekDay', 'contactName', 'peopleQuantity'],
      "properties": {
        "date": 'Fecha de la reserva en formato YYYY-MM-DD',
        "hour": 'Hora de la reserva en formato HH:MM',
        "weekDay": 'Día de la semana de la reserva',
        "contactName": 'Nombre y apellido completo de la persona de contacto',
        "contactNumber": 'Teléfono de contacto (opcional)',
        "peopleQuantity": 'Número de personas',
        "zone": 'Zona seleccionada por el cliente (opcional)',
        "allergies": 'Alergias o requerimientos alimentarios. Usar "no indicado" si el cliente no respondió',
        "specialRequirements": 'Requerimientos especiales opcionales (ocasión especial, accesibilidad, etc.)',
      },
      "additionalProperties": False,
    },
    "type": "function",
  },
  {
    "name": 'update_reservation_request',
    "description": 'Actualiza una reserva existente a partir de su código de reserva.',
    "parameters": {
      "type": "object",
      "required": ['reservation_code'],
      "properties": {
        "reservation_code": "Código de la reserva a actualizar",
        "date": "Nueva fecha en formato YYYY-MM-DD (opcional)",
        "hour": "Nueva hora en formato HH:MM (opcional)",
        "weekDay": "Día de la semana actualizado (opcional)",
        "contactName": "Nombre y apellido actualizado (opcional)",
        "contactNumber": "Teléfono de contacto actualizado (opcional)",
        "peopleQuantity": "Nueva cantidad de personas (opcional)",
        "zone": "Nueva zona (opcional)",
        "allergies": "Alergias o requerimientos actualizados (opcional)",
        "specialRequirements": "Requerimientos especiales actualizados (opcional)",
      },
      "additionalProperties": False,
    },
    "type": "function",
  },
  {
    "name": 'cancel_reservation_request',
    "description": 'Cancela una reserva existente a partir de su código de reserva.',
    "parameters": {
      "type": "object",
      "required": ['reservation_code'],
      "properties": {
        "reservation_code": "Código de la reserva a cancelar",
        "contactNumber": "Teléfono de contacto del titular (opcional, para verificación)",
      },
      "additionalProperties": False,
    },
    "type": "function",
  },
  {
    "name": 'list_orders_for_cancellation_request',
    "description":
      'Lista las reservas del cliente cuando no se dispone del código de reserva y el cliente desea cancelar.',
    "parameters": {
      "type": "object",
      "required": ['contactName'],
      "properties": {
        "contactName": "Nombre y apellido del titular de la reserva",
        "contactNumber": "Teléfono de contacto del titular (opcional)",
      },
      "additionalProperties": False,
    },
    "type": "function",
  },
  {
    "name": 'assign_reservation_to_staff',
    "description":
      'Deriva el caso a personal humano. Usar cuando el cliente confirma una reserva hecha por otro canal, cuando no se puede resolver la consulta, o cuando el grupo supera la capacidad máxima por mesa.',
    "parameters": {
      "type": "object",
      "required": ['full_name', 'message'],
      "properties": {
        "full_name": {
          "type": "string",
          "description": "Nombre completo del cliente",
        },
        "phone": {
          "type": "string",
          "description": "Teléfono del cliente (opcional)",
        },
        "message": {
          "type": "string",
          "description": "Resumen del caso o solicitud del cliente",
        },
      },
      "additionalProperties": False,
    },
    "type": "function",
  },
  {
    "name": 'get_zones',
    "description": 'Consulta todas las zonas existentes administradas dentro del restaurante',
    "parameters": {
      "type": "object",
      "required": [],
      "properties": {},
      "additionalProperties": False,
    },
    "type": "function",
  },
  {
    "name": 'update_customer',
    "description":
      'Actualiza internamente memoria permitida del cliente cuando declara datos personales, ocasiones especiales, alergias, cumpleaños, y otras. No usar para crear, cancelar o actualizar reservas.',
    "parameters": {
      "type": "object",
      "required": ['reason'],
      "properties": {
        "profile": {
          "type": "object",
          "description":
            'Datos base del cliente declarados explícitamente. No inventar datos ni inferirlos si no fueron confirmados.',
          "additionalProperties": False,
          "properties": {
            "firstName": {
              "type": "string",
              "description": 'Primer nombre declarado por el cliente.',
            },
            "lastName": {
              "type": "string",
              "description": 'Apellido declarado por el cliente.',
            },
            "fullName": {
              "type": "string",
              "description": 'Nombre completo declarado por el cliente.',
            },
            "phone": {
              "type": "string",
              "description": 'Teléfono confirmado por el cliente.',
            },
            "email": {
              "type": "string",
              "description": 'Correo electrónico declarado por el cliente.',
            },
            "birthday": {
              "type": "string",
              "description": 'Fecha declarada por el cliente, preferentemente YYYY-MM-DD si está disponible.',
            },
          },
        },
        "details": {
          "type": "object",
          "description": 'Preferencias y notas del cliente. Solo guardar lo que el cliente declara explícitamente.',
          "additionalProperties": False,
          "properties": {
            "preferredZone": {
              "type": "string",
              "description": 'Zona preferida declarada por el cliente, por ejemplo terraza o vista al mar.',
            },
            "allergies": {
              "type": "array",
              "items": {
                "type": "string",
              },
              "description": 'Restricciones alimentarias, alergias o necesidades especiales declaradas.',
            },
            "specialOccasions": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "occasion": {
                    "type": "string",
                    "description": 'Descripción breve de la ocasión',
                  },
                  "date": {
                    "type": "string",
                    "description": 'Fecha en formato YYYY-MM-DD (obligatoria)',
                  },
                },
                "required": ['occasion', 'date'],
              },
              "description": 'Ocasiones especiales a agregar. Ambos campos son obligatorios.',
            },
            "removeAllergies": {
              "type": "array",
              "items": {
                "type": "string",
              },
              "description": 'Alergias a eliminar del perfil',
            },
            "removeSpecialOccasions": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "occasion": {
                    "type": "string",
                  },
                  "date": {
                    "type": "string",
                  },
                },
                "required": ['occasion', 'date'],
              },
              "description": 'Ocasiones especiales a eliminar (deben coincidir exactamente)',
            },
          },
        },
        "reason": {
          "type": "string",
          "description": 'Motivo breve de la actualización para logs.',
        },
      },
      "additionalProperties": False,
    },
    "type": "function",
  },
]
