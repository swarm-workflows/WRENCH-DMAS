#ifndef CENTRALIZED_SCHEDULING_POLICY_H
#define CENTRALIZED_SCHEDULING_POLICY_H

#include <algorithm>
#include <memory>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>
#include <wrench.h>
#include <xbt/log.h>

#include "agents/JobSchedulingAgent.h"
#include "info/HPCSystemDescription.h"
#include "info/HPCSystemStatus.h"
#include "info/JobDescription.h"

XBT_LOG_EXTERNAL_CATEGORY(swarm_dmas);

// Structure to hold system info for centralized decision making
struct HPCSystemInfo {
  std::shared_ptr<wrench::JobSchedulingAgent> agent;
  std::shared_ptr<HPCSystemDescription> description;
  std::shared_ptr<HPCSystemStatus> status;
};

class CentralizedSchedulingPolicy {
  std::string python_script_name_;

public:
  explicit CentralizedSchedulingPolicy(const std::string& python_script_name) : python_script_name_(python_script_name)
  {
  }

  // Select the best system for a job given all available systems' info
  // Returns nullptr if no system can run the job
  std::shared_ptr<wrench::JobSchedulingAgent> select_best_system(const std::shared_ptr<JobDescription>& job_description,
                                                                 const std::vector<HPCSystemInfo>& systems_info)
  {
    if (systems_info.empty())
      return nullptr;

    int to_python[2];
    int from_python[2];

    if (pipe(to_python) == -1 || pipe(from_python) == -1) {
      throw std::runtime_error("Failed to create pipes");
    }

    if (access(python_script_name_.c_str(), F_OK) != 0)
      throw std::runtime_error("Python script not found: " + python_script_name_);

    pid_t pid = fork();
    if (pid == 0) {
      // External Python process
      dup2(to_python[0], STDIN_FILENO);
      dup2(from_python[1], STDOUT_FILENO);

      close(to_python[1]);
      close(from_python[0]);
      close(to_python[0]);
      close(from_python[1]);

      execlp("python3", "python3", python_script_name_.c_str(), nullptr);
      perror("execlp failed");
      exit(1);
    } else {
      // C++ process
      close(to_python[0]);
      close(from_python[1]);

      // Serialize input to JSON
      nlohmann::json j;
      j["job_description"]        = job_description->to_json();
      j["current_simulated_time"] = wrench::S4U_Simulation::getClock();

      // Build array of all systems
      nlohmann::json systems_array = nlohmann::json::array();
      for (const auto& sys_info : systems_info) {
        nlohmann::json sys_json;
        sys_json["system_name"] = sys_info.description->get_name();
        sys_json["description"] = sys_info.description->to_json();
        sys_json["status"]      = sys_info.status->to_json();
        systems_array.push_back(sys_json);
      }
      j["systems"] = systems_array;

      std::string jsonStr = j.dump();
      write(to_python[1], jsonStr.c_str(), jsonStr.size());
      close(to_python[1]);

      // Read response from python
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
        nlohmann::json result = nlohmann::json::parse(response);
        XBT_CVERB(swarm_dmas, "Centralized policy result: %s", result.dump().c_str());

        if (result.contains("selected_system") && result["selected_system"].is_string()) {
          std::string selected_name = result["selected_system"].get<std::string>();

          // Find the agent with the matching system name
          for (const auto& sys_info : systems_info) {
            if (sys_info.description->get_name() == selected_name) {
              return sys_info.agent;
            }
          }
          // System name not found in our list
          XBT_CWARN(swarm_dmas, "Python returned unknown system name: %s", selected_name.c_str());
          return nullptr;
        } else if (result.contains("selected_system") && result["selected_system"].is_null()) {
          // Python explicitly returned null (no feasible system)
          return nullptr;
        } else {
          throw std::runtime_error("Invalid response: 'selected_system' not found or invalid type");
        }
      } catch (const std::exception& e) {
        throw std::runtime_error(std::string("Failed to parse Python response: ") + e.what());
      }
    }
  }
};

#endif // CENTRALIZED_SCHEDULING_POLICY_H
