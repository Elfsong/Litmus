# Litmus
Litmus is the public release of Afterburner Evaluation

# 🚧 Work in Progress
- Import Jinja as Template Engine
- Baseline Distribution Construction

# How to evaluate the code efficiency of a specific model?
```shell
# Step 0. Set up the test environment
venus_test = VenusLitmusTest(lang="python3", number_of_workers=16, case_multiply=64, max_test_packs=512, monolith_timeout=90)

# Step 1. Measure solution distribution on the sandbox (if you have not done so before)
venus_test.run_distribution()

# Step 2. Run the evaluation for a specific model
venus_test.run_evaluation(model_name="google/gemma-3-27b-it", model_display_name="Gemma-3-27B-IT", inference_provider="nebius", efficiency_instruction="time", data_multiply=16, mode="G+E")

```