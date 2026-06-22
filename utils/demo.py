# %% [markdown]
# ## Prepare the environment
# %%
from contextlib import redirect_stderr, redirect_stdout
from importlib import import_module
from io import StringIO
from inspect import Parameter, getmembers, isclass, signature
from pkgutil import iter_modules

from utils import *

utils = UtilityFunctions()
if utils.in_ipython():
	utils.ipython_auto_reload_modules()


SEARCH_PACKAGES = (
	("internal", "utils._internal"),
	("standalone", "utils.standalone"),
)


def build_demo_instance(class_type):
	parameters = signature(class_type).parameters.values()
	required_parameters = [
		parameter
		for parameter in parameters
		if parameter.name != "self"
		and parameter.default is Parameter.empty
		and parameter.kind in (
			Parameter.POSITIONAL_ONLY,
			Parameter.POSITIONAL_OR_KEYWORD,
			Parameter.KEYWORD_ONLY,
		)
	]
	if required_parameters:
		required_names = ", ".join(parameter.name for parameter in required_parameters)
		raise TypeError(f"requires constructor args: {required_names}")
	return class_type()


def get_demo_runner(instance):
	# lib_demo_params: preferred format — GUI in IPython, CLI fallback otherwise.
	if hasattr(instance, 'lib_demo_params'):
		if utils.in_ipython():
			return 'params_demo_gui'
		return 'utils_demo'  # CLI: utils.demo() reads lib_demo_params automatically

	if hasattr(instance, "lib_demo"):
		return "utils_demo"

	demo_method = getattr(instance, "demo", None)
	if callable(demo_method):
		required_parameters = [
			parameter
			for parameter in signature(demo_method).parameters.values()
			if parameter.default is Parameter.empty
			and parameter.kind in (
				Parameter.POSITIONAL_ONLY,
				Parameter.POSITIONAL_OR_KEYWORD,
				Parameter.KEYWORD_ONLY,
			)
		]
		if not required_parameters:
			return "direct_demo"

	return None


def discover_demo_targets():
	demo_targets = []
	skipped_targets = []

	for group_name, package_name in SEARCH_PACKAGES:
		package = import_module(package_name)
		module_infos = sorted(iter_modules(package.__path__), key=lambda item: item.name)

		for module_info in module_infos:
			module_name = f"{package_name}.{module_info.name}"
			module_output = StringIO()
			try:
				with redirect_stdout(module_output), redirect_stderr(module_output):
					module = import_module(module_name)
			except BaseException as exc:
				reason = str(exc)
				captured_output = module_output.getvalue().strip()
				if captured_output:
					reason = f"{reason} | {captured_output}" if reason else captured_output
				skipped_targets.append((group_name, module_name, reason or type(exc).__name__))
				continue

			for class_name, class_type in getmembers(module, isclass):
				if class_type.__module__ != module.__name__ or class_name.startswith("_"):
					continue

				# Skip classes that have no demo capability before attempting instantiation.
				if (not hasattr(class_type, 'lib_demo_params')
						and not hasattr(class_type, 'lib_demo')
						and not hasattr(class_type, 'demo')):
					continue

				try:
					instance_output = StringIO()
					with redirect_stdout(instance_output), redirect_stderr(instance_output):
						demo_instance = build_demo_instance(class_type)
				except BaseException as exc:
					reason = str(exc)
					captured_output = instance_output.getvalue().strip()
					if captured_output:
						reason = f"{reason} | {captured_output}" if reason else captured_output
					skipped_targets.append((group_name, f"{module_name}.{class_name}", reason or type(exc).__name__))
					continue

				runner = get_demo_runner(demo_instance)
				if runner is None:
					continue

				demo_targets.append(
					{
						"key": str(len(demo_targets) + 1),
						"name": f"[{group_name}] {module_info.name}.{class_name}",
						"instance": demo_instance,
						"runner": runner,
					}
				)

	return demo_targets, skipped_targets


def print_demo_targets(demo_targets, skipped_targets):
	print("Select a utils demo target:\n")

	if demo_targets:
		utils.show_demo_menu(
			[{"key": item["key"], "name": item["name"]} for item in demo_targets],
			max_columns=1,
			max_width=120,
		)
	else:
		print("No demo-capable classes were found.\n")

	if skipped_targets:
		print("Skipped targets:")
		for group_name, target_name, reason in skipped_targets:
			print(f"- [{group_name}] {target_name}: {reason}")
		print()


# %% [markdown]
# ## Select a module and run its demo
# %%
demo_targets, skipped_targets = discover_demo_targets()
print_demo_targets(demo_targets, skipped_targets)

selection = input("Enter selection: ").strip()
selected_target = next((item for item in demo_targets if item["key"] == selection), None)

if selected_target is None:
	print("Unknown selection.")
else:
	print(f"Running demo for {selected_target['name']}")
	if selected_target["runner"] == "params_demo_gui":
		# GUI path (IPython/Jupyter): build widget and display it as the cell output.
		from utils.standalone.widget_utils import build_lib_demo_widget
		from IPython.display import display
		output = build_lib_demo_widget(
			selected_target['instance'],
			selected_target['instance'].lib_demo_params,
			title=selected_target['name'],
		)
		display(output)
	elif selected_target["runner"] == "utils_demo":
		output = utils.demo(selected_target["instance"])
	else:
		output = selected_target["instance"].demo()

# %%
