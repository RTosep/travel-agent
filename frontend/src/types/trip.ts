export interface Location {
  name: string;
  address?: string | null;
  city?: string | null;
  district?: string | null;
  adcode?: string | null;
  longitude?: number | null;
  latitude?: number | null;
  source?: string | null;
}

export interface Attraction extends Location {
  rating?: number | null;
  ticket_price?: number | null;
  opening_hours?: string | null;
  category?: string | null;
  recommended_minutes?: number | null;
  note?: string | null;
}

export interface Meal extends Location {
  meal_type?: 'breakfast' | 'lunch' | 'dinner' | 'snack' | null;
  cuisine?: string | null;
  price_per_person?: number | null;
  rating?: number | null;
  note?: string | null;
}

export interface Hotel extends Location {
  star?: number | null;
  price_per_night?: number | null;
  check_in?: string | null;
  check_out?: string | null;
  rating?: number | null;
  note?: string | null;
}

export interface Route {
  mode: 'driving' | 'transit' | 'walking' | 'bicycling';
  origin: Location;
  destination: Location;
  distance_km?: number | null;
  duration_min?: number | null;
}

export interface DailyWeather {
  date?: string | null;
  weather?: string | null;
  high_c?: number | null;
  low_c?: number | null;
  rain_chance_percent?: number | null;
}

export interface Budget {
  total?: number | null;
  transport?: number | null;
  hotel?: number | null;
  meals?: number | null;
  tickets?: number | null;
  other?: number | null;
  currency: string;
}

export interface DayPlan {
  day: number;
  date?: string | null;
  title?: string | null;
  weather?: DailyWeather | null;
  attractions: Attraction[];
  meals: Meal[];
  hotel?: Hotel | null;
  routes: Route[];
  notes: string[];
}

export interface TripPlan {
  title: string;
  destination?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  days: DayPlan[];
  budget?: Budget | null;
  summary?: string | null;
}
