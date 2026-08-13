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
    "param": "comparisonMethod",
    "label": "Сравнение",
    "width": "46%",
    "content": [
      {
        "title": "Предыдущий период",
        "value": "previous_period"
      },
      {
        "title": "Год назад",
        "value": "previous_year"
      }
    ]
  },
  {
    "type": "select",
    "param": "timeStep",
    "label": "Шаг по времени",
    "width": "46%",
    "content": [
      {
        "title": "Авто",
        "value": "auto"
      },
      {
        "title": "День",
        "value": "day"
      },
      {
        "title": "Неделя",
        "value": "week"
      },
      {
        "title": "Месяц",
        "value": "month"
      }
    ]
  }
]};
