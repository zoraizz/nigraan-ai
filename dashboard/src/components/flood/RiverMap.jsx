import { Fragment, useEffect, useMemo, useRef } from 'react'
import {
  CircleMarker,
  MapContainer,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
  Marker,
} from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { waveName } from '../../api/floodTracker.js'
import { FLOOD_CATEGORIES, floodCategory } from '../../config/floodCategories.js'
import { formatCusecs, formatWall } from './timeFormat.js'
import CategoryBadge from './CategoryBadge.jsx'
import './flood.css'

// CARTO Dark Matter. {r} is Leaflet's retina placeholder (@2x or empty).
// Since 25 Sep 2026 the raster endpoint requires a free key (VITE_CARTO_API_KEY).
// Without a key CARTO serves an "API key required" tile, so the map falls back
// to OSM standard tiles, darkened in flood.css (.is-osm-fallback).
const CARTO_DARK_BASE = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

function basemap() {
  const key = String(import.meta.env.VITE_CARTO_API_KEY || '').trim()
  if (!key) {
    return {
      url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      attribution: OSM_ATTRIBUTION,
      subdomains: 'abc',
      fallback: true,
    }
  }
  return {
    url: `${CARTO_DARK_BASE}?key=${encodeURIComponent(key)}`,
    attribution: `${OSM_ATTRIBUTION} &copy; <a href="https://carto.com/attributions">CARTO</a>`,
    subdomains: 'abcd',
    fallback: false,
  }
}
const BASEMAP = basemap()

// Outflow is drawn as marker area, not as a second colour. 100,000 cusecs sits
// under the lowest Low Flood threshold; 800,000 is the upper Indus exceptional
// threshold. The category colour still comes from floodCategories.js.
function radiusForFlow(cusecs) {
  const flow = Number(cusecs)
  if (!Number.isFinite(flow)) return 7
  const t = Math.min(1, Math.max(0, (flow - 100000) / 700000))
  return 7 + t * 13
}

function pointOk(lat, lon) {
  return Number.isFinite(Number(lat)) && Number.isFinite(Number(lon))
}

function lineOk(coords) {
  return Array.isArray(coords)
    && coords.length >= 2
    && coords.every((pair) => Array.isArray(pair) && pointOk(pair[0], pair[1]))
}

function peakIcon(status) {
  const passed = status === 'passed'
  return L.divIcon({
    className: 'flood-peak-icon',
    html: `<span class="flood-peak-dot${passed ? ' is-passed' : ' is-forming'}"></span>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  })
}

function MapFrame({ positions }) {
  const map = useMap()
  const positionsRef = useRef(positions)
  positionsRef.current = positions
  const fitted = useRef(false)

  useEffect(() => {
    const container = map.getContainer()
    let framing = false
    const frame = () => {
      if (framing) return
      framing = true
      map.invalidateSize()
      if (!fitted.current) {
        const pts = positionsRef.current
        if (pts.length > 0 && container.clientHeight >= 40) {
          fitted.current = true
          if (pts.length === 1) map.setView(pts[0], 8)
          else map.fitBounds(pts, { padding: [36, 36] })
        }
      }
      framing = false
    }
    frame()
    const observer = new ResizeObserver(frame)
    observer.observe(container)
    return () => observer.disconnect()
  }, [map])

  return null
}

function FocusVillage({ village }) {
  const map = useMap()
  const id = village?.id
  const lat = village?.lat
  const lon = village?.lon
  useEffect(() => {
    if (!id || !pointOk(lat, lon)) return
    map.panTo([lat, lon], { animate: true })
  }, [map, id, lat, lon])
  return null
}

function Legend() {
  return (
    <div className="pointer-events-none absolute bottom-6 left-2 z-[500] max-w-[11rem] rounded-lg border border-[#1b4a33]/80 bg-[#071a0e]/92 p-2 text-[10px] leading-snug text-[#c5d9cc] shadow-lg">
      <p className="mb-1 font-semibold uppercase tracking-wide text-[#8aa898]">Outflow category</p>
      <ul className="space-y-0.5">
        {FLOOD_CATEGORIES.map((item) => (
          <li key={item.key} className="flex items-center gap-1.5">
            <span className="h-1.5 w-4 rounded-full" style={{ backgroundColor: item.color }} />
            <span>{item.label}</span>
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-[#8aa898]">Marker size follows outflow. Pulsing ring marks the peak.</p>
    </div>
  )
}

export default function RiverMap({ situation, selectedVillageId, onSelectVillage }) {
  const barrages = situation?.barrages ?? []
  const reaches = situation?.reaches ?? []
  const peaks = situation?.peaks ?? []
  const villages = situation?.at_risk_villages ?? []
  const selected = villages.find((village) => village.id === selectedVillageId) ?? null

  const positions = []
  barrages.forEach((barrage) => {
    if (pointOk(barrage.lat, barrage.lon)) positions.push([Number(barrage.lat), Number(barrage.lon)])
  })
  villages.forEach((village) => {
    if (pointOk(village.lat, village.lon)) positions.push([Number(village.lat), Number(village.lon)])
  })

  const barrageByName = new Map(barrages.map((barrage) => [barrage.name, barrage]))
  const icons = useMemo(() => ({
    forming: peakIcon('forming'),
    passed: peakIcon('passed'),
  }), [])

  return (
    <div className={`flood-map${BASEMAP.fallback ? ' is-osm-fallback' : ''} relative h-full min-h-[460px] overflow-hidden lg:min-h-0 rounded-xl border border-[#1b4a33]/80`}>
      <MapContainer
        center={[29.7, 70.4]}
        zoom={6}
        className="h-full w-full"
        scrollWheelZoom
        zoomControl
      >
        <TileLayer
          attribution={BASEMAP.attribution}
          url={BASEMAP.url}
          subdomains={BASEMAP.subdomains}
          maxZoom={19}
        />
        <MapFrame positions={positions} />
        <FocusVillage village={selected} />

        {reaches.map((reach) => {
          if (!lineOk(reach.coords)) return null
          const color = floodCategory(reach.category).color
          const key = `${reach.from}-${reach.to}`
          return (
            <Fragment key={key}>
              <Polyline
                positions={reach.coords}
                pathOptions={{ color: '#04140c', weight: 8, opacity: 0.85, lineCap: 'round', lineJoin: 'round' }}
              />
              <Polyline
                positions={reach.coords}
                pathOptions={{ color, weight: 4.5, opacity: 0.95, lineCap: 'round', lineJoin: 'round' }}
              >
                <Popup>
                  <p className="font-semibold">{reach.from} to {reach.to}</p>
                  <p className="mt-1"><CategoryBadge category={reach.category} /></p>
                  <p className="mt-1 text-[11px] text-[#9dbdac]">Reach category is the higher of the two barrages. Estimate, not a gauge trace.</p>
                </Popup>
              </Polyline>
            </Fragment>
          )
        })}

        {villages.map((village) => {
          if (!pointOk(village.lat, village.lon)) return null
          const active = village.id === selectedVillageId
          return (
            <Fragment key={village.id}>
              {active && (
                <CircleMarker
                  center={[village.lat, village.lon]}
                  radius={16}
                  pathOptions={{ color: '#3ddc84', weight: 2, fillOpacity: 0, opacity: 1 }}
                  interactive={false}
                />
              )}
              <CircleMarker
                center={[village.lat, village.lon]}
                radius={active ? 6 : 4.5}
                pathOptions={{
                  color: '#04140c',
                  weight: 1,
                  fillColor: '#f4f7f5',
                  fillOpacity: 0.95,
                }}
                eventHandlers={{ click: () => onSelectVillage?.(village.id) }}
              >
                <Tooltip direction="left" offset={[-6, 0]}>
                  {village.name}
                </Tooltip>
                <Popup>
                  <p className="font-semibold">{village.name}</p>
                  <p className="text-[12px] text-[#c5d9cc]">{village.district}</p>
                  <p className="mt-1 text-[12px]">Est. arrival {formatWall(village.eta)}</p>
                </Popup>
              </CircleMarker>
            </Fragment>
          )
        })}

        {barrages.map((barrage) => {
          if (!pointOk(barrage.lat, barrage.lon)) return null
          const color = floodCategory(barrage.category).color
          return (
            <CircleMarker
              key={barrage.name}
              center={[barrage.lat, barrage.lon]}
              radius={radiusForFlow(barrage.outflow_cusecs)}
              pathOptions={{
                color: '#04140c',
                weight: 1,
                fillColor: color,
                fillOpacity: 0.92,
              }}
            >
              <Tooltip permanent direction="right" offset={[8, 0]} className="flood-name-tip">
                {barrage.name}
              </Tooltip>
              <Popup>
                <p className="font-semibold">{barrage.name}</p>
                <p className="mt-1"><CategoryBadge category={barrage.category} /></p>
                <p className="mt-1 font-mono text-[12px]">Outflow {formatCusecs(barrage.outflow_cusecs)}</p>
                <p className="font-mono text-[12px] text-[#c5d9cc]">Inflow {formatCusecs(barrage.inflow_cusecs)}</p>
                <p className="mt-1 text-[11px] capitalize text-[#9dbdac]">{barrage.trend || 'trend not reported'}. Category follows outflow.</p>
              </Popup>
            </CircleMarker>
          )
        })}

        {peaks.map((peak) => {
          const barrage = barrageByName.get(peak.barrage)
          if (!barrage || !pointOk(barrage.lat, barrage.lon)) return null
          const forming = peak.status === 'forming'
          return (
            <Marker
              key={`${peak.wave_id || 'wave'}-${peak.barrage}`}
              position={[barrage.lat, barrage.lon]}
              icon={forming ? icons.forming : icons.passed}
              zIndexOffset={800}
            >
              <Popup>
                <p className="font-semibold">
                  {forming ? 'Peak forming' : 'Peak passed'} at {peak.barrage}
                </p>
                <p className="text-[12px] text-[#c5d9cc]">{waveName(peak)}</p>
                <p className="mt-1 font-mono text-[12px]">{formatWall(peak.peak_time)}</p>
                <p className="font-mono text-[12px]">Peak outflow {formatCusecs(peak.peak_outflow_cusecs)}</p>
                <p className="mt-1 text-[11px] text-[#9dbdac]">Modelled wave marker, not a gauge.</p>
              </Popup>
            </Marker>
          )
        })}
      </MapContainer>
      <Legend />
    </div>
  )
}
