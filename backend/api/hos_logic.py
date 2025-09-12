# api/hos_logic.py

import math

class TripSimulator:
    def __init__(self, total_distance, pickup_distance, cycle_hours_used):
        # Constants
        self.AVG_SPEED_MPH = 55
        self.TIME_INCREMENT_HR = 0.25  # Simulate in 15-minute chunks

        # Input parameters
        self.total_trip_distance = total_distance
        self.distance_to_pickup = pickup_distance
        self.initial_cycle_hours = cycle_hours_used
        
        # State variables
        self.events = []
        self.total_distance_driven = 0
        self.distance_since_fuel = 0
        self.time_elapsed_hr = 0
        self.current_day = 1
        
        # HOS rule trackers
        self.cycle_hours_remaining = 70 - self.initial_cycle_hours
        self.window_time_remaining = 14.0
        self.drive_time_remaining_in_window = 11.0
        self.drive_time_since_last_break = 0.0

    def _add_event(self, status, duration_hr, reason=""):
        """Helper to add an event and update timers."""
        event = {
            "day": self.current_day,
            "status": status,
            "start_time": self.time_elapsed_hr,
            "duration": duration_hr,
            "reason": reason
        }
        self.events.append(event)
        self.time_elapsed_hr += duration_hr
        
        if status in ["Driving", "On Duty (Not Driving)"]:
            self.cycle_hours_remaining -= duration_hr
            self.window_time_remaining -= duration_hr
        
        if self.time_elapsed_hr >= self.current_day * 24:
            self.current_day += 1

    def _take_10_hour_reset(self):
        """Simulates a full 10-hour reset."""
        self._add_event("Off Duty", 10.0, "10-Hour Reset")
        self.window_time_remaining = 14.0
        self.drive_time_remaining_in_window = 11.0
        self.drive_time_since_last_break = 0.0

    def _take_30_min_break(self):
        """Simulates the mandatory 30-minute break."""
        self._add_event("Off Duty", 0.5, "30-Min Break")
        self.drive_time_since_last_break = 0.0
    
    def _take_34_hour_restart(self):
        """Simulates a full 34-hour restart."""
        self._add_event("Off Duty", 34.0, "34-Hour Restart")
        self.cycle_hours_remaining = 70.0

    def plan_trip(self):
        # Phase 1: Drive to pickup
        self._drive_segment(self.distance_to_pickup)
        
        # Phase 2: Pickup stop
        self._add_event("On Duty (Not Driving)", 1.0, "Pickup")

        # Phase 3: Drive to dropoff
        distance_to_dropoff = self.total_trip_distance - self.distance_to_pickup
        self._drive_segment(distance_to_dropoff)

        # Phase 4: Dropoff stop
        self._add_event("On Duty (Not Driving)", 1.0, "Dropoff")
        
        return self.events

    def _drive_segment(self, segment_distance):
        distance_driven_in_segment = 0
        while distance_driven_in_segment < segment_distance:
            # Check if a 10-hour reset is needed before starting to drive
            if self.drive_time_remaining_in_window <= 0 or self.window_time_remaining <= self.TIME_INCREMENT_HR:
                self._take_10_hour_reset()
                continue

            # Check if we have enough cycle time for the next driving increment
            if self.cycle_hours_remaining < self.TIME_INCREMENT_HR:
                self._take_34_hour_restart()
                continue
                
            # Check if a 30-min break is needed
            if self.drive_time_since_last_break >= 8.0:
                self._take_30_min_break()
                continue

            # All checks passed, let's drive for one increment
            distance_this_increment = min(
                self.AVG_SPEED_MPH * self.TIME_INCREMENT_HR,
                segment_distance - distance_driven_in_segment
            )
            time_this_increment = distance_this_increment / self.AVG_SPEED_MPH
            
            self._add_event("Driving", time_this_increment)
            
            # Update driving-specific trackers
            self.drive_time_remaining_in_window -= time_this_increment
            self.drive_time_since_last_break += time_this_increment
            self.total_distance_driven += distance_this_increment
            self.distance_since_fuel += distance_this_increment
            distance_driven_in_segment += distance_this_increment

            # Check for fuel stop
            if self.distance_since_fuel >= 1000:
                self._add_event("On Duty (Not Driving)", 0.5, "Fueling")
                self.distance_since_fuel = 0