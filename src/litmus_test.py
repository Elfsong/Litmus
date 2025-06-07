# coding: utf-8

# Author: Du Mingzhe (mingzhe@nus.edu.sg)
# Date: 2025-06-06

import time
import json
import utils
import random
import requests
import textwrap
from tqdm import tqdm
from typing import Any
from datasets import Dataset
from tabulate import tabulate
from datasets import load_dataset
from multiprocessing.dummy import Pool as ThreadPool

class LitmusTest:
    def __init__(self, lang, number_of_workers, case_multiply, max_test_packs, monolith_timeout) -> None:
        self.lang = lang
        self.case_multiply = case_multiply
        self.max_test_packs = max_test_packs
        self.monolith_timeout = monolith_timeout
        self.number_of_workers = number_of_workers
    
    @classmethod
    def run_execution(cls, lang: str, solution_code: str, instance: Any, case_multiply: int, timeout: int) -> dict:
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
            test_code = utils.render_template(
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

class VenusLitmusTest(LitmusTest):
    def __init__(self, lang, number_of_workers, case_multiply, max_test_packs, monolith_timeout) -> None:
        super().__init__(lang, number_of_workers, case_multiply, max_test_packs, monolith_timeout)
        self.venus_dataset = load_dataset("Elfsong/Venus", lang, split="train")
        self.leetcode_dataset = load_dataset("Elfsong/leetcode_data", split="train")
        self.leetcode_len = len(self.leetcode_dataset)
        self.venus_dict = {int(instance['question_id']): instance for instance in self.venus_dataset}

    def run_distribution(self):
        distribution_data = list()
        for index, instance in enumerate(self.leetcode_dataset):
            problem_id = instance['problem_id']
            print(f"[+] Processing Problem [{problem_id}]...")

            # 1. Instance Check
            if not instance['test_case_runners']: continue
            if not instance['test_case_runners'][self.lang]: continue
            if not instance['test_case_evaluator']: continue
            if not instance['solutions']: continue
            if not instance['solutions'][self.lang]: continue

            # 2. Prepare the solution code
            solution_list = list()

            # 2.1 Canonical Solutions
            for solution in instance['solutions'][self.lang]:
                solution_list.append(solution)

            # 2.2 Human Solutions
            if problem_id in self.venus_dict:
                rt_list = self.venus_dict[problem_id]['rt_list']
                mm_list = self.venus_dict[problem_id]['mm_list']
                for solution in rt_list + mm_list:
                    solution_list.append(solution['code'])
            
            # 3. Solution Deduplication
            solution_list = list(set(solution_list))
            
            # 4. Construct Test Packs
            solution_list = random.sample(solution_list, min(self.max_test_packs, len(solution_list)))
            test_packs = [(self.lang, solution, instance, self.case_multiply, self.monolith_timeout) for solution in solution_list]

            print(f'[+] Problem {problem_id} [{index}/{self.leetcode_len}] - {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')

            # 5. Parallel Evaluation
            execution_results = list()
            with ThreadPool(self.number_of_workers) as pool:
                with tqdm(total=len(test_packs), desc='Solution Evaluation') as pbar:
                    for result in pool.imap(lambda args: LitmusTest.run_execution(*args), test_packs):
                        execution_results.append(result)
                        pbar.update(1)

            # 6. Display the results
            headers = ["Passed", "Status", "Time (ms)", "Memory (kb)", "Integral (ms * kb)"]
            table = []
            for result in execution_results:
                row = [
                    '🟢' if result['passed'] else '🔴',
                    result['status'],
                    f"{result['time']:.2f}",
                    f"{result['memory']:.2f}",
                    f"{str(result['integral'])}"
                ]
                table.append(row)
            print(tabulate(table, headers=headers, tablefmt="fancy_outline"))

            # 7. Verify Solutions
            verified_solutions = list()
            for (solution, result) in zip(solution_list, execution_results):
                verified_solutions.append({
                    'code': solution, 
                    'status': str(result['status']),
                    'passed': bool(result['passed']),
                    'time': float(result['time']),
                    'memory': float(result['memory']),
                    'integral': float(result['integral'])
                })

            data = {
                "problem_id": int(instance['problem_id']),
                "title": str(instance['title']),
                "question_content": str(instance['question_content']),
                "difficulty": str(instance['difficulty']),
                "tags": list(instance['tags']),
                "code_prompt": str(instance['code_prompt']['python3']),
                "test_case_generator": str(instance['test_case_generator']),
                "test_case_evaluator": str(instance['test_case_evaluator']),
                "test_case_runners": str(instance['test_case_runners']["python3"]),
                "test_cases": str(instance['test_cases']),
                "solutions": verified_solutions
            }
            distribution_data.append(data)

        # 8. Push Data to HF
        new_leetcode_dataset = Dataset.from_list(distribution_data)
        new_leetcode_dataset.push_to_hub(f"Elfsong/venus_{self.lang}_distribution", 'distribution', private=True)

    def run_evaluation(self, model_name, model_display_name, inference_provider, efficiency_instruction, data_multiply=1, mode="G+E"):
        # Distribution Dataset
        distribution_dataset = load_dataset(f"Elfsong/venus_{self.lang}_distribution", "distribution")

        # Generation (G)
        if mode in ["G", "G+E"]:
            test_packs = list()
            for instance in tqdm(distribution_dataset, desc='Generating solutions...'):
                try:
                    generated_solution = self.run_generation(inference_provider, model_name, instance, efficiency_instruction, self.lang, temperature=0, max_token=16384)
                except Exception as e:
                    print(f"[-] Generation Error: {e}")
                    generated_solution = ""
                finally:
                    test_packs.append({"problem_id": int(instance['problem_id']), "solution": generated_solution})
            ds = Dataset.from_list(test_packs)
            ds.push_to_hub(f"Elfsong/venus_{self.lang}_generation", f"model_{model_display_name}_{efficiency_instruction}", private=True)

        # Evaluation (E)
        if mode in ["E", "G+E"]:
            generation_dataset = load_dataset(f"Elfsong/venus_{self.lang}_generation", f"model_{model_display_name}_{efficiency_instruction}", split="train")
            
            solutions = dict()
            for instance in generation_dataset:
                solutions[int(instance['problem_id'])] = instance['solution']
            
            test_packs = [(solutions[int(instance['problem_id'])], instance, self.case_multiply, self.monolith_timeout) for instance in distribution_dataset]
            test_packs = test_packs * data_multiply
            
            results = list()
            with ThreadPool(self.number_of_workers) as pool:
                with tqdm(total=len(test_packs), desc='Solution Evaluation') as pbar:
                    for result in pool.imap(lambda args: LitmusTest.run_execution(*args), test_packs):
                        results.append(result)
                        pbar.update(1)
                        
            # Score Calculation
            # TODO(mingzhe): Move it as a class method
            instance_list = list()
            for instance, test_pack, result in zip(distribution_dataset.repeat(data_multiply), test_packs, results):
                time_distribution = [s['time'] for s in instance['solutions'] if s['passed']]
                memory_distribution = [s['memory'] for s in instance['solutions'] if s['passed']]
                integral_distribution = [s['integral'] for s in instance['solutions'] if s['passed']]

                status = {
                    "problem_id": int(instance['problem_id']),
                    "passed": bool(result['passed']),
                    "precentile_time": utils.percentage_position(result['time'], time_distribution),
                    "precentile_memory": utils.percentage_position(result['memory'], memory_distribution),
                    "precentile_integral": utils.percentage_position(result['integral'], integral_distribution),
                    "absolute_time": float(result['time']),
                    "absolute_memory": float(result['memory']),
                    "absolute_integral": float(result['integral']),
                    "solution_code": str(test_pack[0]),
                }

                instance_list.append(status)
            
            scores = {"total_c": 0, "pass_c": 0, "time_s": 0,"memory_s": 0, "integral_s": 0}
            for instance in instance_list:
                scores["total_c"] += 1
                if instance['passed']:
                    scores["pass_c"] += 1
                    scores["time_s"] += instance['precentile_time']
                    scores["memory_s"] += instance['precentile_memory']
                    scores["integral_s"] += instance['precentile_integral']
            
            scores["pass_score"] = scores["pass_c"] / scores["total_c"]
            scores["time_score"] = scores["time_s"] / scores["total_c"]
            scores["memory_score"] = scores["memory_s"] / scores["total_c"]
            scores["integral_score"] = scores["integral_s"] / scores["total_c"]

            result = (f"Venus [{model_display_name}] Pass@1:{scores['pass_score']:.2f} Time_Precent:{scores['time_score']:.2f} Memory_Precent:{scores['memory_score']:.2f} Integral_Precent:{scores['integral_score']:.2f}")
            # print(result)
                
            # Save the results
            ds = Dataset.from_list(instance_list)
            ds.push_to_hub(f"Elfsong/venus_{self.lang}_evaluation", f"model_{model_display_name}_{efficiency_instruction}", private=True)

class AppsLitmusTest(LitmusTest):
    def __init__(self, lang, number_of_workers, case_multiply, max_test_packs, monolith_timeout) -> None:
        super().__init__(lang, number_of_workers, case_multiply, max_test_packs, monolith_timeout)
        # TODO: Move code here 

if __name__ == "__main__":
    venus_test = VenusLitmusTest(lang="python3", number_of_workers=16, case_multiply=64, max_test_packs=512, monolith_timeout=90)
    # Get the distribution of each problem (it takes a long long time, be careful if you truely want to run it)
    venus_test.run_distribution()

    # Run the evaluation for each model
    venus_test.run_evaluation(model_name="google/gemma-3-27b-it", model_display_name="Gemma-3-27B-IT", inference_provider="nebius", efficiency_instruction="time", data_multiply=16, mode="G+E")
    
    
    