"""Plantillas JSON del motor de formularios."""

REVISION_2026 = {
  "id": "revision_2026",
  "version": 1,
  "title": "Revisión Equip. Embarcado",
  "sections": [
    {
      "id": "sec_tipo",
      "title": "1. Tipo de revisión",
      "fields": [
        {
          "key": "tipo_revision",
          "type": "single_choice",
          "label": "Tipo",
          "required": True,
          "options": [
            {"value": "INVENTARIO", "label": "Inventario"},
            {"value": "BITACORA", "label": "Bitácora"}
          ],
          "ui": "button_group"
        },
        {
          "key": "numero_bus",
          "type": "text",
          "label": "Bus",
          "required": True,
          "readonly": True,
          "maps_to": "numero_bus"
        },
        {
          "key": "patio",
          "type": "select",
          "label": "Patio",
          "required": True,
          "options_source": "patios"
        },
        {
          "key": "tecnico_nombre",
          "type": "text",
          "label": "Técnico",
          "required": True,
          "readonly": True
        }
      ]
    },
    {
      "id": "sec_gps",
      "title": "2. GPS",
      "fields": [
        {
          "key": "gps",
          "type": "single_choice",
          "label": "Estado GPS",
          "required": True,
          "options": [
            {"value": "FUNCIONA", "label": "Funciona", "color": "success"},
            {"value": "CORTO", "label": "Corto", "color": "warning"},
            {"value": "MOJADO", "label": "Mojado", "color": "info"}
          ],
          "ui": "button_group"
        }
      ]
    },
    {
      "id": "sec_vand",
      "title": "3. Vandalismo",
      "fields": [
        {
          "key": "vandalismo",
          "type": "single_choice",
          "label": "Vandalismo",
          "required": False,
          "options": [
            {"value": "NINGUNO", "label": "Ninguno"},
            {"value": "PERDIDA_GPS", "label": "Pérdida de GPS"},
            {"value": "CORTE_ARNES", "label": "Corte de arnés"},
            {"value": "ROBO_SIMCARD", "label": "Robo de SIMCARD"}
          ],
          "ui": "button_group"
        }
      ]
    },
    {
      "id": "sec_sim",
      "title": "4–6. SIM / Adecuación / CTAP",
      "fields": [
        {
          "key": "simcard",
          "type": "select",
          "label": "SIMCARD",
          "required": False,
          "options": [
            {"value": "", "label": "—"},
            {"value": "DETERIORO_REEMPLAZO", "label": "Deterioro – Reemplazo"},
            {"value": "OK", "label": "OK"},
            {"value": "NO_APLICA", "label": "No aplica"}
          ],
          "visible_when": {"field": "vandalismo", "in": ["ROBO_SIMCARD", "PERDIDA_GPS"]}
        },
        {
          "key": "adecuacion_electrica",
          "type": "select",
          "label": "Adecuación eléctrica",
          "required": False,
          "options": [
            {"value": "", "label": "—"},
            {"value": "ADECUADA", "label": "Adecuada"},
            {"value": "NO_ADECUADA", "label": "No adecuada"}
          ]
        },
        {
          "key": "ctap",
          "type": "select",
          "label": "CTAP",
          "required": False,
          "options": [
            {"value": "", "label": "—"},
            {"value": "FUNCIONA", "label": "Funciona"},
            {"value": "DANADA", "label": "Dañada"},
            {"value": "NO_TIENE", "label": "No tiene"}
          ]
        }
      ]
    },
    {
      "id": "sec_radio",
      "title": "7. Radio base",
      "fields": [
        {
          "key": "radio",
          "type": "matrix",
          "label": "Radio base",
          "required": False,
          "rows": [
            {"key": "radio_conexion", "label": "Conexión"},
            {"key": "radio_instalacion", "label": "Instalación"},
            {"key": "radio_perilla", "label": "Perilla"},
            {"key": "radio_pedal", "label": "Pedal"},
            {"key": "radio_pantalla", "label": "Pantalla"}
          ],
          "columns": [
            {"value": "SIMCARD", "label": "SIMCARD"},
            {"value": "SI", "label": "SI"},
            {"value": "NO", "label": "NO"},
            {"value": "FUNCIONA", "label": "FUNCIONA"},
            {"value": "DANADA", "label": "DAÑADA"}
          ]
        }
      ]
    },
    {
      "id": "sec_informe",
      "title": "8. Informe técnico",
      "fields": [
        {
          "key": "informe_tecnico",
          "type": "textarea",
          "label": "Informe técnico",
          "required": True,
          "rows": 4,
          "placeholder": "Hallazgos, acciones realizadas, pendientes…"
        }
      ]
    }
  ]
}
