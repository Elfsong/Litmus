# coding: utf-8

# Author: Du Mingzhe (mingzhe@nus.edu.sg)
# Date: 2025-06-06

import json
import jinja2
import requests
import textwrap
from typing import Any

def render_template(template_path: str, **kwargs) -> str:
    with open(template_path, 'r') as f:
        template = jinja2.Template(f.read())
    return template.render(**kwargs)

def run_evaluation(lang: str, solution_code: str, instance: Any, case_multiply: int, timeout: int) -> dict:
    response = {'passed': False, 'time': float('inf'), 'memory': float('inf'), 'integral': float('inf'), 'status': 'error'}
    try:
        # Construct Test Code
        test_case_runners = instance['test_case_runners'][lang]
        solution_code = test_case_runners.replace('==Code Submission==', solution_code.strip())
        solution_code = textwrap.indent(solution_code.strip(), "    ")
        test_case_evaluator = instance['test_case_evaluator'].strip()
        test_case_evaluator = textwrap.indent(test_case_evaluator, "    ")

        test_cases = json.loads(instance['test_cases'])
        test_case_list_str = json.dumps(test_cases, indent=4)
        test_code = render_template(
            './Litmus/src/templates/evaluation.txt', 
            solution_code=solution_code, 
            test_case_evaluator=test_case_evaluator, 
            test_case_list=test_case_list_str, 
            case_multiply=case_multiply
        )

        # Submit Test Code to Monolith
        data = {
            'code': test_code,
            'language': 'python',
            'libraries': [],
            'timeout': timeout,
            'run_profiling': True
        }
        monolith_response = requests.post(f'https://monolith.cool/execute', json=data, timeout=(120, timeout))
        if monolith_response.status_code == 200:
            monolith_response = monolith_response.json()

            response['status'] = monolith_response['status']
            if monolith_response["status"] == "success":
                response['passed'] = True if monolith_response['output_dict']['stdout'] == 'Success\n' else False
                response['time'] = monolith_response['output_dict']['duration']
                response['memory'] = monolith_response['output_dict']['peak_memory']
                response['integral'] = monolith_response['output_dict']['integral']
        elif monolith_response.status_code == 413:
            response['status'] = "too large"
        else:
            raise requests.exceptions.RequestException("API Error: " + str(monolith_response.content), monolith_response.status_code)
    except requests.exceptions.ReadTimeout as e:
        response['status'] = 'timeout (server)'
    except requests.exceptions.ConnectionError as e:
        response['status'] = 'timeout (client)'
    except Exception as e:
        print("Evaluation Error: ", e)
        response['status'] = 'error'
    finally:
        return response