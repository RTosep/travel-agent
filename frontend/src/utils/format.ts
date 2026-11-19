import type { Attraction, DailyWeather, Hotel, Meal, Route } from '../types';

export const MODE_LABEL: Record<Route['mode'], string> = {
  driving: '驾车',
  transit: '公交/地铁',
  walking: '步行',
  bicycling: '骑行',
};

export const MEAL_LABEL: Record<NonNullable<Meal['meal_type']>, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '小吃',
};

export function formatWeather(weather: DailyWeather): string {
  const parts: string[] = [];
  if (weather.weather) parts.push(weather.weather);
  if (weather.low_c != null || weather.high_c != null) {
    parts.push(`${weather.low_c ?? '?'}~${weather.high_c ?? '?'}℃`);
  }
  if (weather.rain_chance_percent != null) {
    parts.push(`降雨 ${weather.rain_chance_percent}%`);
  }
  return parts.join(' · ');
}

export function attractionMeta(attraction: Attraction): string {
  return [
    attraction.rating != null ? `${attraction.rating} 分` : null,
    attraction.ticket_price != null ? `门票 ${attraction.ticket_price} 元` : null,
    attraction.category,
    attraction.address,
  ]
    .filter(Boolean)
    .join(' · ');
}

export function mealMeta(meal: Meal): string {
  return [
    meal.meal_type ? MEAL_LABEL[meal.meal_type] : null,
    meal.price_per_person != null ? `人均 ${meal.price_per_person} 元` : null,
    meal.rating != null ? `${meal.rating} 分` : null,
    meal.address,
  ]
    .filter(Boolean)
    .join(' · ');
}

export function hotelMeta(hotel: Hotel): string {
  return [
    hotel.star != null ? `${hotel.star} 星` : null,
    hotel.price_per_night != null ? `${hotel.price_per_night} 元/晚` : null,
    hotel.rating != null ? `${hotel.rating} 分` : null,
  ]
    .filter(Boolean)
    .join(' · ');
}

export function routeMeta(route: Route): string {
  return [
    MODE_LABEL[route.mode],
    route.distance_km != null ? `${route.distance_km} km` : null,
    route.duration_min != null ? `${route.duration_min} 分钟` : null,
  ]
    .filter(Boolean)
    .join(' · ');
}
