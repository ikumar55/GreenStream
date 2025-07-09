import json
import logging
from datetime import datetime, timezone
import os

# GridStatus library would be installed in the Lambda layer
try:
    import gridstatus
except ImportError:
    # Fallback for local development
    gridstatus = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Fuel type to CO2 conversion factors (kg CO2/MWh)
FUEL_CO2_FACTORS = {
    'Nuclear': 0,
    'Hydro': 0,
    'Wind': 0,
    'Solar': 0,
    'Geothermal': 0,
    'Biomass': 230,
    'Coal': 1000,
    'Natural Gas': 450,
    'Oil': 650,
    'Other': 500,
    'Unknown': 500
}

def calculate_carbon_intensity(fuel_mix):
    """Calculate carbon intensity from fuel mix data."""
    if not fuel_mix:
        return 500.0  # Default fallback
    
    total_mwh = 0
    total_co2 = 0
    
    for fuel_type, mwh in fuel_mix.items():
        if mwh and mwh > 0:
            total_mwh += mwh
            co2_factor = FUEL_CO2_FACTORS.get(fuel_type, 500)
            total_co2 += mwh * co2_factor
    
    if total_mwh > 0:
        # Convert kg CO2/MWh to g CO2/kWh
        intensity_kg_mwh = total_co2 / total_mwh
        intensity_g_kwh = intensity_kg_mwh * 1000 / 1000  # kg/MWh to g/kWh
        return intensity_g_kwh
    else:
        return 500.0  # Default fallback

def lambda_handler(event, context):
    """AWS Lambda handler for GridStatus carbon intensity."""
    try:
        # Get ISO from query parameters
        iso = event.get('queryStringParameters', {}).get('iso', 'NYISO')
        
        if not gridstatus:
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'GridStatus library not available',
                    'iso': iso,
                    'intensity': 500.0,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            }
        
        # Get fuel mix data from GridStatus
        iso_obj = getattr(gridstatus, iso)()
        fuel_mix = iso_obj.get_fuel_mix()
        
        # Calculate carbon intensity
        intensity = calculate_carbon_intensity(fuel_mix)
        
        response = {
            'iso': iso,
            'intensity': round(intensity, 2),
            'fuel_mix': fuel_mix,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source': 'GridStatus'
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(response)
        }
        
    except Exception as e:
        logger.error(f"Error in GridStatus Lambda: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'iso': iso if 'iso' in locals() else 'unknown',
                'intensity': 500.0,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        }

# For local testing
if __name__ == "__main__":
    test_event = {
        'queryStringParameters': {
            'iso': 'NYISO'
        }
    }
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2)) 