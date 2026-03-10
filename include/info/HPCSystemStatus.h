#ifndef HPC_SYSTEM_STATUS_H
#define HPC_SYSTEM_STATUS_H

#include <cstddef>
#include <nlohmann/json.hpp>

class HPCSystemStatus {
  size_t current_num_avaibable_nodes_;
  double current_job_start_time_estimate_;
  size_t queue_length_;

public:
  HPCSystemStatus(size_t current_num_avaibable_nodes, double current_job_start_time_estimate, size_t queue_length)
      : current_num_avaibable_nodes_(current_num_avaibable_nodes)
      , current_job_start_time_estimate_(current_job_start_time_estimate)
      , queue_length_(queue_length)
  {
  }

  size_t get_current_num_avaibable_nodes() const { return current_num_avaibable_nodes_; }
  double get_current_job_start_time_estimate() const { return current_job_start_time_estimate_; }
  size_t get_queue_length() const { return queue_length_; }

  nlohmann::json to_json() const
  {
    return {{"current_num_available_nodes", current_num_avaibable_nodes_},
            {"current_job_start_time_estimate", current_job_start_time_estimate_},
            {"queue_length", queue_length_}};
  }
};

#endif // HPC_SYSTEM_STATUS_H