export const SCENES = ['flooded_street', 'flooded_farmland', 'collapsed_house', 'damaged_building', 'damaged_road', 'broken_bridge', 'landslide', 'debris', 'relief_camp', 'other_disaster']
export const NEEDS = ['rescue', 'shelter', 'medical', 'food_water', 'road_clearance']
export const DEPTHS = ['none', 'ankle', 'knee', 'waist', 'chest', 'above_head']
export const words = (value) => String(value ?? 'unknown').replaceAll('_', ' ')
export const LEVELS = {
  none: 'text-risk-low-bright border-risk-low',
  partial: 'text-risk-medium-bright border-risk-medium',
  destroyed: 'text-risk-high-bright border-risk-high',
}
