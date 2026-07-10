# Services

## `power_insight.set_value`

Set the accumulated total of a Power Insight **total / accumulation** sensor. Use
this to seed a sensor with a known starting value — for example to carry over
historical totals when adopting the integration.

### Target

A Power Insight `sensor` entity with an accumulated total (state class *total*),
such as *Total cost savings*, *Total operating costs*, or *Total export
compensation*.

### Fields

| Field | Required | Description |
|---|---|---|
| `value` | yes | The new accumulated total to set. |

### Example

```yaml
service: power_insight.set_value
target:
  entity_id: sensor.home_combined_total_cost_savings
data:
  value: 42.0
```

!!! tip
    From then on the sensor keeps integrating its rate on top of the value you
    set — so pick the value that reflects the true running total at the moment
    you call the service.
