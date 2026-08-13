/**
 * Ready control configuration and Params bindings.
 * Route: editor_js_control. Technical parameter names and aliases are language-neutral.
 */
module.exports = {controls: [
  {
    "type": "range-datepicker",
    "paramFrom": "dateFrom",
    "paramTo": "dateTo",
    "label": "Period",
    "width": "94%"
  },
  {
    "type": "select",
    "param": "comparisonMethod",
    "label": "Comparison",
    "width": "46%",
    "content": [
      {
        "title": "Previous period",
        "value": "previous_period"
      },
      {
        "title": "Previous year",
        "value": "previous_year"
      }
    ]
  },
  {
    "type": "select",
    "param": "timeStep",
    "label": "Time step",
    "width": "46%",
    "content": [
      {
        "title": "Auto",
        "value": "auto"
      },
      {
        "title": "Day",
        "value": "day"
      },
      {
        "title": "Week",
        "value": "week"
      },
      {
        "title": "Month",
        "value": "month"
      }
    ]
  }
]};
