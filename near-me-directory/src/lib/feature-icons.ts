// Feature icon mapping - maps facility feature keys to Lucide icon names
// Used across the application for consistent feature display

export const FEATURE_ICON_MAP: Record<string, string> = {
  accessible: 'accessibility',
  adult_change: 'accessibility',
  all_gender: 'users',
  ambulant: 'accessibility',
  baby_care_room: 'baby',
  baby_change: 'baby',
  changing_places: 'accessibility',
  drinking_water: 'glassWater',
  dump_point: 'trash2',
  female: 'venus',
  key_required: 'key',
  lh_transfer: 'accessibility',
  male: 'mars',
  mens_pad_disposal: 'trash2',
  mlak: 'key',
  parking: 'squareParking',
  parking_accessible: 'squareParking',
  payment_required: 'creditCard',
  rh_transfer: 'accessibility',
  sanitary_disposal: 'trash2',
  sharps_disposal: 'syringe',
  shower: 'showerHead',
  unisex: 'users',
} as const;

// Display labels for features (can differ from feature key names)
export const FEATURE_LABELS: Record<string, string> = {
  accessible: 'Accessible',
  adult_change: 'Adult Change',
  all_gender: 'All Gender',
  ambulant: 'Ambulant',
  baby_care_room: 'Baby Care Room',
  baby_change: 'Baby Change',
  changing_place: 'Changing Place',
  changing_places: 'Changing Places',
  drinking_water: 'Drinking Water',
  dump_point: 'Dump Point',
  female: 'Female',
  key_required: 'Key Required',
  lh_transfer: 'LH Transfer',
  male: 'Male',
  mens_pad_disposal: 'Mens Disposal',
  mlak: 'MLAK',
  parking: 'Parking',
  parking_accessible: 'Accessible Parking',
  payment_required: 'Payment Required',
  rh_transfer: 'RH Transfer',
  sanitary_disposal: 'Sanitary Disposal',
  sharps_disposal: 'Sharps Disposal',
  shower: 'Shower',
  unisex: 'Unisex',
} as const;

// High-priority features shown on facility cards and headers
export const HIGH_PRIORITY_FEATURES: string[] = [
  'accessible',
  'baby_change', 
  'unisex',
  'parking',
  'baby_care_room',
  'shower',
  'drinking_water',
  'all_gender',
  'female',
  'male',
];

// Get icon name for a feature key (fallback to info if not found)
export function getFeatureIcon(featureKey: string): string {
  return FEATURE_ICON_MAP[featureKey] || 'info';
}

// Get display label for a feature key (fallback to formatted key)
export function getFeatureLabel(featureKey: string): string {
  return FEATURE_LABELS[featureKey] || featureKey.replace(/_/g, ' ');
}