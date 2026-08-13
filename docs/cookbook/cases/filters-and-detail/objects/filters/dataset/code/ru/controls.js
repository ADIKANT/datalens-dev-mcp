/**
 * Готовая конфигурация контролов и их связи с Params.
 * Route: editor_js_control. Технические имена параметров и aliases оставлены без перевода.
 */
module.exports = {controls: [
  {
    "type": "range-datepicker",
    "paramFrom": "dateFrom",
    "paramTo": "dateTo",
    "label": "Период",
    "width": "94%"
  },
  {
    "type": "select",
    "param": "category",
    "label": "Категория",
    "searchable": true,
    "width": "46%",
    "content": [
      {
        "title": "Все",
        "value": ""
      },
      {
        "title": "A",
        "value": "a"
      },
      {
        "title": "B",
        "value": "b"
      }
    ]
  },
  {
    "type": "select",
    "param": "status",
    "label": "Статус",
    "multiselect": true,
    "width": "46%",
    "content": [
      {
        "title": "Готово",
        "value": "ready"
      },
      {
        "title": "Требует внимания",
        "value": "warning"
      }
    ]
  }
]};
