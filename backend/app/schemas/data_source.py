from typing import Literal

# "measured": a real device or satellite (e.g. Landsat ST_B10). "simulated": physical
# model or demo seed. "third_party": outside data that is neither, such as Open-Meteo
# weather. Every response carrying such data states which one it is.
DataSource = Literal["measured", "simulated", "third_party"]
# Uploaded readings come from a device or the simulator, never from a third party.
MeasurementSource = Literal["measured", "simulated"]
