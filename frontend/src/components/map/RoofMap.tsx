import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { geoJSON, latLngBounds } from 'leaflet'
import type { PathOptions } from 'leaflet'
import { Circle, GeoJSON, MapContainer, TileLayer, Tooltip, useMap } from 'react-leaflet'
import type { Roof } from '../../api/types'
import { albedoColor, roofRadiusM } from '../../lib/roofs'
import { number } from '../../lib/format'
import type { MapCity } from '../../hooks/useCitySelection'

type RoofState = 'selected' | 'chosen' | 'plain'

// Highlighted roofs get a contrasting outline; the rest are outlined in their own albedo
// colour, so the scale still reads when a whole city is in view.
const OUTLINE: Record<Exclude<RoofState, 'plain'>, { color: string; weight: number }> = {
  selected: { color: '#152f43', weight: 4 },
  chosen: { color: '#007961', weight: 3 },
}
const PLAIN_WEIGHT = 1
const FOCUS = { padding: [70, 70] as [number, number], maxZoom: 18, animate: false }
const FIT_ALL = { padding: [30, 30] as [number, number], animate: false }
const FOCUS_ZOOM = 18

/** Frames every roof once they arrive: the city centre alone shows a handful of the 576. */
function FitRoofs({ roofs }: { roofs: Roof[] }): null {
  const map = useMap()
  const hasRoofs = roofs.length > 0
  useEffect(() => {
    if (hasRoofs) map.fitBounds(latLngBounds(roofs.map(roof => [roof.lat, roof.lon])), FIT_ALL)
    // Only on arrival: refitting on every filter change would move the map under the user.
  }, [map, hasRoofs])
  return null
}

function FocusRoof({ roof }: { roof: Roof | null }): null {
  const map = useMap()
  useEffect(() => {
    if (!roof) return
    if (roof.geometry) map.fitBounds(geoJSON(roof.geometry).getBounds(), FOCUS)
    else map.setView([roof.lat, roof.lon], FOCUS_ZOOM, { animate: false })
  }, [map, roof])
  return null
}

function RoofShape({
  roof,
  state,
  onSelect,
}: {
  roof: Roof
  state: RoofState
  onSelect: (id: string) => void
}): ReactNode {
  const fill = albedoColor(roof.albedo)
  const outline = state === 'plain' ? { color: fill, weight: PLAIN_WEIGHT } : OUTLINE[state]
  const style: PathOptions = { fillColor: fill, fillOpacity: 0.8, ...outline }
  const events = { click: () => onSelect(roof.roof_id) }
  const tooltip = (
    <Tooltip>
      <strong>{roof.roof_id}</strong>
      <br />
      Albedo {number(roof.albedo, 2)} · Priority {number(roof.priority_score, 2)}
    </Tooltip>
  )
  if (!roof.geometry) {
    return (
      <Circle
        center={[roof.lat, roof.lon]}
        radius={roofRadiusM(roof.area_m2)}
        pathOptions={style}
        eventHandlers={events}
      >
        {tooltip}
      </Circle>
    )
  }
  // GeoJSON reads its style once, so the state is part of the key to redraw a highlighted roof.
  return (
    <GeoJSON
      key={`${roof.roof_id}:${state}`}
      data={roof.geometry}
      style={style}
      eventHandlers={events}
    >
      {tooltip}
    </GeoJSON>
  )
}

function MapLegend(): ReactNode {
  return (
    <div className="map-legend">
      <strong>Roof albedo</strong>
      <div className="albedo-gradient" />
      <div className="legend-ends">
        <span>0 · Dark / hotter</span>
        <span>1 · Light / cooler</span>
      </div>
      <div className="budget-legend">
        <i /> Within budget <span className="selection-line" /> Selected roof
      </div>
    </div>
  )
}

export function RoofMap({
  roofs,
  chosenIds,
  selected,
  onSelect,
  city,
}: {
  roofs: Roof[]
  chosenIds: Set<string>
  selected: Roof | null
  onSelect: (id: string) => void
  city: MapCity
}): ReactNode {
  const stateOf = (roof: Roof): RoofState =>
    selected?.roof_id === roof.roof_id
      ? 'selected'
      : chosenIds.has(roof.roof_id)
        ? 'chosen'
        : 'plain'
  return (
    <div className="map-frame">
      <MapContainer center={city.center} zoom={city.zoom} className="roof-map" zoomControl>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        {roofs.map(roof => (
          <RoofShape key={roof.roof_id} roof={roof} state={stateOf(roof)} onSelect={onSelect} />
        ))}
        <FitRoofs roofs={roofs} />
        <FocusRoof roof={selected} />
      </MapContainer>
      <div className="map-location">
        {city.name.toUpperCase()}, {city.country.toUpperCase()}
        <span>{city.center.map(value => value.toFixed(4)).join(' · ')}</span>
      </div>
      <MapLegend />
    </div>
  )
}
