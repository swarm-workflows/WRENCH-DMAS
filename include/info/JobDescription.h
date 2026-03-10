#ifndef JOB_DESCRIPTION_H
#define JOB_DESCRIPTION_H

#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <wrench/util/UnitParser.h> //sg_size_t

enum class JobType { HPC, AI, HYBRID, STORAGE };

class JobDescription {
  int job_id_;
  int user_id_;
  int group_id_;
  JobType job_type_;
  double submission_time_;
  sg_size_t walltime_;
  size_t num_nodes_;
  bool needs_gpu_;
  double requested_memory_gb_;
  double requested_storage_gb_;
  std::string hpc_site_;
  std::string hpc_system_;

public:
  JobDescription(int job_id, int user_id, int group_id, JobType job_type, double submission_time, sg_size_t walltime,
                 size_t num_nodes, bool needs_gpu, double requested_memory_gb, double requested_storage_gb,
                 const std::string& hpc_site, const std::string& hpc_system)
      : job_id_(job_id)
      , user_id_(user_id)
      , group_id_(group_id)
      , job_type_(job_type)
      , submission_time_(submission_time)
      , walltime_(walltime)
      , num_nodes_(num_nodes)
      , needs_gpu_(needs_gpu)
      , requested_memory_gb_(requested_memory_gb)
      , requested_storage_gb_(requested_storage_gb)
      , hpc_site_(hpc_site)
      , hpc_system_(hpc_system)
  {
  }

  explicit JobDescription(const nlohmann::json& j)
      : job_id_(j["job_id"])
      , user_id_(j["user_id"])
      , group_id_(j["group_id"])
      , job_type_(string_to_job_type(j["job_type"]))
      , submission_time_(j["submission_time"])
      , walltime_(j["walltime"])
      , num_nodes_(j["num_nodes"])
      , needs_gpu_(j["needs_gpu"])
      , requested_memory_gb_(j["requested_memory_gb"])
      , requested_storage_gb_(j["requested_storage_gb"])
      , hpc_site_(j["hpc_site"])
      , hpc_system_(j["hpc_system"])
  {
  }

  // getters
  int get_job_id() const { return job_id_; }
  int get_user_id() const { return user_id_; }
  int get_group_id() const { return group_id_; }
  JobType get_job_type() const { return job_type_; }
  double get_submission_time() const { return submission_time_; }
  sg_size_t get_walltime() const { return walltime_; }
  size_t get_num_nodes() const { return num_nodes_; }
  bool needs_gpu() const { return needs_gpu_; }
  double get_requested_memory_gb() const { return requested_memory_gb_; }
  double get_requested_storage_gb() const { return requested_storage_gb_; }
  const std::string& get_hpc_site() const { return hpc_site_; }
  const std::string& get_hpc_system() const { return hpc_system_; }

  static JobType string_to_job_type(const std::string& s)
  {
    static const std::unordered_map<std::string, JobType> EnumStrings{
        {"HPC", JobType::HPC}, {"AI", JobType::AI}, {"HYBRID", JobType::HYBRID}, {"STORAGE", JobType::STORAGE}};

    auto it = EnumStrings.find(s);
    if (it != EnumStrings.end()) {
      return it->second;
    } else {
      throw std::out_of_range("Invalid JobType string: " + s);
    }
  }

  static const std::string& job_type_to_string(JobType type)
  {
    static const std::unordered_map<JobType, std::string> EnumToString{
        {JobType::HPC, "HPC"}, {JobType::AI, "AI"}, {JobType::HYBRID, "HYBRID"}, {JobType::STORAGE, "STORAGE"}};

    auto it = EnumToString.find(type);
    if (it != EnumToString.end()) {
      return it->second;
    } else {
      throw std::out_of_range("Invalid JobType");
    }
  }

  nlohmann::json to_json() const
  {
    return {{"job_id", job_id_},
            {"user_id", user_id_},
            {"group_id", group_id_},
            {"job_type", job_type_to_string(job_type_)},
            {"submission_time", submission_time_},
            {"walltime", walltime_},
            {"num_nodes", num_nodes_},
            {"needs_gpu", needs_gpu_},
            {"requested_memory_gb", requested_memory_gb_},
            {"requested_storage_gb", requested_storage_gb_},
            {"hpc_site", hpc_site_},
            {"hpc_system", hpc_system_}};
  }
};
#endif // JOB_DESCRIPTION_H