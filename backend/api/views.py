# api/views.py
from django.shortcuts import render
import os
import json
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import dotenv
import os.path

# load .env from backend directory explicitly
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
dotenv.load_dotenv(dotenv_path)

# export MAPQUEST_API_KEY
MAPQUEST_API_KEY = os.getenv('MAPQUEST_API_KEY')


@csrf_exempt  # Use this for development to allow POST requests without a CSRF token
def get_route_data(request):
    if request.method == 'POST':
        try:
            if not MAPQUEST_API_KEY:
                return JsonResponse({'error': 'Missing MAPQUEST_API_KEY'}, status=500)

            # Decode the request body
            data = json.loads(request.body.decode('utf-8'))
            start_location = data.get('start')
            end_location = data.get('end')

            if not start_location or not end_location:
                return JsonResponse({'error': 'Missing start or end location'}, status=400)

            # Use params to ensure correct escaping
            params = {
                'key': MAPQUEST_API_KEY,
                'from': start_location,
                'to': end_location,
                'outFormat': 'json',
                'ambiguities': 'ignore',
                'routeType': 'fastest',
                'doReverseGeocode': 'false',
                'enhancedNarrative': 'false',
                'avoidTimedConditions': 'false'
            }

            # Make the API call with a timeout
            response = requests.get("https://www.mapquestapi.com/directions/v2/route", params=params, timeout=10)
            response.raise_for_status()  # Raise an exception for bad status codes

            route_info = response.json()

            # Check for routing errors from MapQuest
            status = route_info.get('info', {}).get('statuscode')
            if status != 0:
                messages = route_info.get('info', {}).get('messages', [])
                return JsonResponse({'error': 'MapQuest error', 'statuscode': status, 'messages': messages}, status=400)

            # Extract the necessary data
            route = route_info.get('route', {})
            distance = route.get('distance')

            # 1) Prefer the top-level shape points if present (flat list: [lat,lng,lat,lng,...])
            shape = route.get('shape') or {}
            shape_points = shape.get('shapePoints') if isinstance(shape.get('shapePoints'), list) else []

            # 2) Fallback: gather shapePoints from maneuvers if top-level not present
            if not shape_points:
                for leg in route.get('legs', []):
                    for maneuver in leg.get('maneuvers', []):
                        mshape = maneuver.get('shape')
                        if mshape and isinstance(mshape.get('shapePoints'), list):
                            shape_points.extend(mshape.get('shapePoints', []))

            # 3) Fallback: gather lat/lng from maneuver startPoints (MapQuest may include objects)
            lat_lng_pairs = []
            if not shape_points:
                for leg in route.get('legs', []):
                    for maneuver in leg.get('maneuvers', []):
                        # try startPoint -> latLng pattern
                        start_pt = maneuver.get('startPoint') or maneuver.get('startPoint', {})
                        latlng = None
                        if isinstance(start_pt, dict):
                            if 'latLng' in start_pt and isinstance(start_pt['latLng'], dict):
                                latlng = start_pt['latLng']
                            elif 'lat' in start_pt and 'lng' in start_pt:
                                latlng = {'lat': start_pt.get('lat'), 'lng': start_pt.get('lng')}
                        # also try 'startPoint' directly as lat/lng
                        if latlng and 'lat' in latlng and 'lng' in latlng:
                            try:
                                lat = float(latlng['lat'])
                                lng = float(latlng['lng'])
                                lat_lng_pairs.append([lat, lng])
                            except (TypeError, ValueError):
                                continue

            # If we have flat shape_points convert to lat/lng pairs
            if shape_points and not lat_lng_pairs:
                # Ensure even number of coordinates
                if len(shape_points) % 2 != 0:
                    shape_points = shape_points[:-1]
                lat_lng_pairs = [[float(shape_points[i]), float(shape_points[i+1])]
                                 for i in range(0, len(shape_points), 2)]

            if not lat_lng_pairs:
                return JsonResponse({'error': 'No route coordinates returned by MapQuest.'}, status=400)

            return JsonResponse({
                'distance': distance,
                'routePath': lat_lng_pairs
            })

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)
        except requests.exceptions.RequestException as re:
            return JsonResponse({'error': 'MapQuest request failed', 'details': str(re)}, status=502)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Only POST method is allowed'}, status=405)
