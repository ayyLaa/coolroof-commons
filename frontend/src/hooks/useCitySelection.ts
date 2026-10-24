import { useState } from 'react'
import cityConfig from '../../schema/cities.json'
import type { ClimateComparison } from '../api/types'
import { useClimateComparison } from './resources'
import type { Resource } from './useApiResource'

/** name is what the backend stores in roofs.city and filters /roofs?city= by. */
export interface MapCity {
  id: string
  name: string
  country: string
  center: [number, number]
  zoom: number
}
interface CitySelection {
  city: MapCity
  cities: MapCity[]
  setCity: (id: string) => void
  climate: Resource<ClimateComparison>
  comparisonAvailable: boolean
}
const CONFIGURED_CITIES = cityConfig as MapCity[]

export function useCitySelection(): CitySelection {
  const climate = useClimateComparison()
  const [selected, setSelected] = useState('athens')
  const cities = CONFIGURED_CITIES
  const city = cities.find(item => item.id === selected) ?? cities[0]
  const setCity = (id: string): void => {
    if (cities.some(item => item.id === id)) setSelected(id)
  }
  return { city, cities, climate, comparisonAvailable: climate.data !== null, setCity }
}
