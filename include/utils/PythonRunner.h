#ifndef PYTHON_RUNNER_H
#define PYTHON_RUNNER_H

#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <sys/wait.h>
#include <unistd.h>

/**
 * @brief Execute a Python script with JSON input and return JSON output.
 *
 * @param script_path Path to the Python script to execute.
 * @param input JSON object to pass to the script via stdin.
 * @return nlohmann::json The parsed JSON response from the script.
 * @throws std::runtime_error if pipes fail, script not found, or JSON parsing fails.
 */
inline nlohmann::json run_python_script(const std::string& script_path, const nlohmann::json& input)
{
  int to_python[2];
  int from_python[2];

  if (pipe(to_python) == -1 || pipe(from_python) == -1)
    throw std::runtime_error("Failed to create pipes");

  if (access(script_path.c_str(), F_OK) != 0)
    throw std::runtime_error("Python script not found: " + script_path);

  pid_t pid = fork();
  if (pid == 0) {
    // Child process: become the Python interpreter
    dup2(to_python[0], STDIN_FILENO);
    dup2(from_python[1], STDOUT_FILENO);

    close(to_python[1]);
    close(from_python[0]);
    close(to_python[0]);
    close(from_python[1]);

    execlp("python3", "python3", script_path.c_str(), nullptr);
    perror("execlp failed");
    exit(1);
  } else {
    // Parent process: communicate with Python
    close(to_python[0]);
    close(from_python[1]);

    // Send JSON input to Python
    std::string jsonStr = input.dump();
    write(to_python[1], jsonStr.c_str(), jsonStr.size());
    close(to_python[1]); // Signal EOF to Python

    // Read JSON response from Python
    std::string response;
    char buffer[256];
    ssize_t count;
    while ((count = read(from_python[0], buffer, sizeof(buffer) - 1)) > 0) {
      buffer[count] = '\0';
      response += buffer;
    }
    close(from_python[0]);
    waitpid(pid, nullptr, 0);

    try {
      return nlohmann::json::parse(response);
    } catch (const std::exception& e) {
      throw std::runtime_error(std::string("Failed to parse Python response: ") + e.what() +
                               "\nResponse was: " + response);
    }
  }
}

#endif // PYTHON_RUNNER_H
