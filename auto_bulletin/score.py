import json
import requests

def generate_cve_url(cve_id):
    """Generate the URL for a given CVE ID."""
    year, number = cve_id.split("-")[1], cve_id.split("-")[2]
    return f"https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/{year}/{number[:-3]}xxx/CVE-{year}-{number}.json"

def extract_cvss_scores(cve_data):
    """
    Extracts all CVSS scores from the provided CVE JSON data.
    Specifically checks 'cna' and 'adp' containers for 'metrics' data.
    
    :param cve_data: JSON object containing the CVE data
    :return: List of CVSS scores (floats), or empty list if not found
    """
    cvss_scores = []

    try:
        # Handle 'cna' container (where 'metrics' is a list of dictionaries)
        if 'cna' in cve_data['containers']:
            for container in cve_data['containers']['cna'].get('metrics', []):
                if isinstance(container, dict):
                    # Check both 'cvssV3_1' and 'cvssV3_0'
                    if 'cvssV3_3' in container:
                        cvss_scores.append(container['cvssV3_3'].get('baseScore', None))
                    elif 'cvssV3_2' in container:
                        cvss_scores.append(container['cvssV3_2'].get('baseScore', None))
                    elif 'cvssV3_1' in container:
                        cvss_scores.append(container['cvssV3_1'].get('baseScore', None))
                    elif 'cvssV3_0' in container:
                        cvss_scores.append(container['cvssV3_0'].get('baseScore', None))
                    elif 'cvssV4_0' in container:
                        cvss_scores.append(container['cvssV4_0'].get('baseScore', None))


        # Handle 'adp' container (where 'metrics' is a list of dictionaries, and other types exist)
        if 'adp' in cve_data['containers']:
            for container in cve_data['containers']['adp']:
                for metric in container.get('metrics', []):
                    if isinstance(metric, dict):
                        # Check both 'cvssV3_1' and 'cvssV3_0'
                        if 'cvssV3_3' in metric:
                            cvss_scores.append(metric['cvssV3_3'].get('baseScore', None))
                        elif 'cvssV3_2' in metric:
                            cvss_scores.append(metric['cvssV3_2'].get('baseScore', None))
                        elif 'cvssV3_1' in metric:
                            cvss_scores.append(metric['cvssV3_1'].get('baseScore', None))
                        elif 'cvssV3_0' in metric:
                            cvss_scores.append(metric['cvssV3_0'].get('baseScore', None))
                        elif 'cvssV4_0' in metric:
                            cvss_scores.append(metric['cvssV4_0'].get('baseScore', None))

        return cvss_scores
    except Exception as e:
        print(f"Error extracting CVSS scores: {e}")
        return []


def fetch_cve_data(cve_id):
    """Fetch CVE data from the generated URL."""
    url = generate_cve_url(cve_id)
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching CVE data for {cve_id}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error fetching CVE data: {e}")
        return None


def calculate_cvss_range(cve_ids):
    """
    Calculates the minimum and maximum CVSS scores from a list of CVE IDs.
    Handles errors in fetching data, and returns "-" if all scores are N/A or if there's an error.
    
    :param cve_ids: List of CVE identifiers
    :return: (min_score, max_score) or "-" if all are N/A or on error
    """
    all_scores = []

    for cve_id in cve_ids:
        cve_data = fetch_cve_data(cve_id)
        if cve_data:
            scores = extract_cvss_scores(cve_data)
            all_scores.extend(scores)
        else:
            # If fetch fails, we add None to indicate an issue
            all_scores.append(None)
    
    # Filter out None and N/A values from the scores
    valid_scores = [score for score in all_scores if score is not None]

    # If no valid scores are found, return "-"
    if not valid_scores:
        return "-"
    
    # Get the min and max values from valid scores
    min_score = min(valid_scores)
    max_score = max(valid_scores)
    
    # If all the scores are equal, return only one score
    if min_score == max_score:
        return str(min_score)
    
    # Return the range as "min - max"
    return f"{min_score} - {max_score}"



