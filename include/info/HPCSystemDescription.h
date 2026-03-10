#ifndef HPC_SYSTEM_DESCRIPTION_H
#define HPC_SYSTEM_DESCRIPTION_H

#include <nlohmann/json.hpp>
#include <string>

enum class HPCSystemType { HPC, AI, HYBRID, STORAGE };

class HPCSystemDescription {
  std::string name_;
  std::string site_;
  HPCSystemType type_;
  size_t num_nodes_;
  double node_speed_;
  int memory_amount_in_gb_;
  int storage_amount_in_gb_;
  bool has_gpu_;
  std::string network_interconnect_;

public:
  HPCSystemDescription(const std::string& name, const std::string& site, HPCSystemType type, size_t num_nodes,
                       double node_speed, int memory_amount_in_gb, int storage_amount_in_gb, bool has_gpu,
                       const std::string& network_interconnect)
      : name_(name)
      , site_(site)
      , type_(type)
      , num_nodes_(num_nodes)
      , node_speed_(node_speed)
      , memory_amount_in_gb_(memory_amount_in_gb)
      , storage_amount_in_gb_(storage_amount_in_gb)
      , has_gpu_(has_gpu)
      , network_interconnect_(network_interconnect)
  {
  }

  static std::shared_ptr<HPCSystemDescription> create(const std::string& system_name,
                                                      const std::vector<std::string>& host_list)
  {
    auto system_site = wrench::S4U_Simulation::getClusterProperty(system_name, "site");
    auto system_type = HPCSystemDescription::string_to_hpc_system_type(
        wrench::S4U_Simulation::getClusterProperty(system_name, "type"));
    auto system_num_compute_nodes = host_list.size() - 1;
    auto system_node_speed        = wrench::S4U_Simulation::getHostFlopRate(host_list.front());
    auto system_memory_amount_in_gb =
        std::stoi(wrench::S4U_Simulation::getClusterProperty(system_name, "memory_amount_in_gb"));
    auto system_storage_amount_in_gb =
        std::stod(wrench::S4U_Simulation::getClusterProperty(system_name, "storage_amount_in_gb"));
    auto system_has_gpu              = (wrench::S4U_Simulation::getClusterProperty(system_name, "has_gpu") == "True");
    auto system_network_interconnect = wrench::S4U_Simulation::getClusterProperty(system_name, "network_interconnect");

    return std::make_shared<HPCSystemDescription>(
        system_name, system_site, system_type, system_num_compute_nodes, system_node_speed, system_memory_amount_in_gb,
        system_storage_amount_in_gb, system_has_gpu, system_network_interconnect);
  }

  // Getters
  const std::string& get_name() const { return name_; }
  const char* get_cname() const { return name_.c_str(); }
  const std::string& get_site() const { return site_; }
  HPCSystemType get_type() const { return type_; }
  size_t get_num_nodes() const { return num_nodes_; }
  double get_node_speed() const { return node_speed_; }
  int get_memory_amount_in_gb() const { return memory_amount_in_gb_; }
  int get_storage_amount_in_gb() const { return storage_amount_in_gb_; }
  const std::string& get_network_interconnect() const { return network_interconnect_; }
  bool has_gpu() const { return has_gpu_; }

  static HPCSystemType string_to_hpc_system_type(const std::string& s)
  {
    static const std::unordered_map<std::string, HPCSystemType> EnumStrings{{"HPC", HPCSystemType::HPC},
                                                                            {"AI", HPCSystemType::AI},
                                                                            {"HYBRID", HPCSystemType::HYBRID},
                                                                            {"STORAGE", HPCSystemType::STORAGE}};

    auto it = EnumStrings.find(s);
    if (it != EnumStrings.end()) {
      return it->second;
    } else {
      throw std::out_of_range("Invalid HPCSystemType string: " + s);
    }
  }

  static const std::string& hpc_system_type_to_string(HPCSystemType type)
  {
    static const std::unordered_map<HPCSystemType, std::string> EnumStrings{{HPCSystemType::HPC, "HPC"},
                                                                            {HPCSystemType::AI, "AI"},
                                                                            {HPCSystemType::HYBRID, "HYBRID"},
                                                                            {HPCSystemType::STORAGE, "STORAGE"}};

    auto it = EnumStrings.find(type);
    if (it != EnumStrings.end()) {
      return it->second;
    } else {
      throw std::out_of_range("Invalid HPCSystemType enum");
    }
  }

  nlohmann::json to_json() const
  {
    return {{"name", name_},
            {"site", site_},
            {"type", hpc_system_type_to_string(type_)},
            {"num_nodes", num_nodes_},
            {"node_speed", node_speed_},
            {"memory_amount_in_gb", memory_amount_in_gb_},
            {"storage_amount_in_gb", storage_amount_in_gb_},
            {"has_gpu", has_gpu_},
            {"network_interconnect", network_interconnect_}};
  }
};

#endif // HPC_SYSTEM_DESCRIPTION_H