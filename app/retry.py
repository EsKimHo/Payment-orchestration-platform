#exponential backoff logic 
import time
import random


def call_with_retries(gateway, amount, currency, max_attempts=2, base_delay=1):
   
    attempts = []

    for attempt_number in range(1, max_attempts + 1):
        result = gateway.charge(amount, currency)
        attempts.append(result)

        if result["status"] == "success":
            return attempts, result

        if attempt_number < max_attempts:
            delay = base_delay * (2 ** (attempt_number - 1)) + random.uniform(0, 0.5)
            time.sleep(delay)
             #exponential backoff with jitter 
    return attempts, attempts[-1]  # every attempt failed