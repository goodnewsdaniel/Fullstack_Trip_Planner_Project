# api/views.py

import os
import json
import logging
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .hos_logic import TripSimulator
import dotenv

# Setup logging
logger = logging.getLogger(__name__)

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
dotenv.load_dotenv(dotenv_path)

MAPQUEST_API_KEY = os.getenv('MAPQUEST_API_KEY')


def get_route_from_mapquest(start, end):
    """Helper function to call MapQuest API."""
    url = f"https://www.mapquestapi.com/directions/v2/route?key={MAPQUEST_API_KEY}&from={start}&to={end}&outFormat=json&routeType=fastest"
    response = requests.get(url)
    response.raise_for_status()
    route_info = response.json()
    if route_info['info']['statuscode'] != 0:
        raise Exception(
            f"MapQuest could not find a route from {start} to {end}")
    return route_info['route']


def format_logs(events):
    """Helper function to group events by day for the log sheets."""
    daily_logs = {}
    for event in events:
        day = event['day']
        if day not in daily_logs:
            daily_logs[day] = {"date": f"Day {day}", "events": []}

        # Convert elapsed hours to HH:MM format for the log
        start_hr = int(event['start_time'] % 24)
        start_min = int((event['start_time'] * 60) % 60)

        end_time = event['start_time'] + event['duration']
        end_hr = int(end_time % 24)
        end_min = int((end_time * 60) % 60)

        daily_logs[day]['events'].append({
            "status": event['status'],
            "startTime": f"{start_hr:02d}:{start_min:02d}",
            "endTime": f"{end_hr:02d}:{end_min:02d}",
            "reason": event.get('reason', '')
        })
    return list(daily_logs.values())


@csrf_exempt
def plan_trip_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    if not MAPQUEST_API_KEY:
        return JsonResponse({'error': 'MapQuest API key not configured'}, status=500)

    try:
        data = json.loads(request.body.decode('utf-8'))

        # Validate required fields
        required_fields = ['currentLocation',
                           'pickupLocation', 'dropoffLocation']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({'error': f'Missing required field: {field}'}, status=400)

        current_loc = data['currentLocation']
        pickup_loc = data['pickupLocation']
        dropoff_loc = data['dropoffLocation']
        cycle_hours = float(data.get('cycleHoursUsed', 0))

        # 1. Get route data from MapQuest for both segments
        route_to_pickup = get_route_from_mapquest(current_loc, pickup_loc)
        route_to_dropoff = get_route_from_mapquest(pickup_loc, dropoff_loc)

        # 2. Extract distances and combine route paths
        dist_to_pickup = route_to_pickup['distance']
        total_dist = dist_to_pickup + route_to_dropoff['distance']

        # Combine shape points for the full map polyline
        full_route_shape = route_to_pickup['shape']['shapePoints'] + \
            route_to_dropoff['shape']['shapePoints']
        lat_lng_pairs = [[full_route_shape[i], full_route_shape[i+1]]
                         for i in range(0, len(full_route_shape), 2)]

        # 3. Run the HOS simulation
        simulator = TripSimulator(total_dist, dist_to_pickup, cycle_hours)
        events = simulator.plan_trip()

        # 4. Format the output
        stops = [
            {"location": pickup_loc, "reason": "Pickup"},
            {"location": dropoff_loc, "reason": "Dropoff"}
        ]
        # Add break/fuel stops to the map visualization
        for event in events:
            if event['reason'] and "Break" in event['reason'] or "Fueling" in event['reason']:
                # Note: Getting the exact location of mid-trip stops is complex.
                # For this assessment, we'll simplify and just add a named stop.
                stops.append({"location": f"Mid-trip Stop",
                             "reason": event['reason']})

        daily_logs = format_logs(events)

        return JsonResponse({
            'routePath': lat_lng_pairs,
            'stops': stops,
            'dailyLogs': daily_logs
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)
    except ValueError as ve:
        return JsonResponse({'error': str(ve)}, status=400)
    except requests.exceptions.RequestException as re:
        logger.error(f"MapQuest API error: {str(re)}")
        return JsonResponse({'error': 'Failed to get route from MapQuest'}, status=502)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)
