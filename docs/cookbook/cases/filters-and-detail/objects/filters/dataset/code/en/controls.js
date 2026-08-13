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
    "param": "category",
    "label": "Category",
    "searchable": true,
    "width": "46%",
    "content": [
      {
        "title": "All",
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
    "label": "Status",
    "multiselect": true,
    "width": "46%",
    "content": [
      {
        "title": "Ready",
        "value": "ready"
      },
      {
        "title": "Needs attention",
        "value": "warning"
      }
    ]
  }
]};
