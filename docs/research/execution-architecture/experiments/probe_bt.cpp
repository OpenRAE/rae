// Test fixture: halting the tree does not stop an independently running effect.
#include <behaviortree_cpp/bt_factory.h>
#include <atomic>
#include <chrono>
#include <iostream>
#include <thread>

std::atomic<int> effects{0};
std::atomic<int> halts{0};
std::thread worker;

class Action : public BT::StatefulActionNode {
 public:
  Action(const std::string& name, const BT::NodeConfig& config)
      : BT::StatefulActionNode(name, config) {}
  static BT::PortsList providedPorts() { return {}; }
  BT::NodeStatus onStart() override {
    worker = std::thread([] {
      std::this_thread::sleep_for(std::chrono::milliseconds(500));
      effects++;
    });
    return BT::NodeStatus::RUNNING;
  }
  BT::NodeStatus onRunning() override {
    return effects.load() ? BT::NodeStatus::SUCCESS : BT::NodeStatus::RUNNING;
  }
  void onHalted() override { halts++; }
};

int main() {
  BT::BehaviorTreeFactory factory;
  factory.registerNodeType<Action>("Effect");
  auto tree = factory.createTreeFromText(
    R"(<root BTCPP_format="4"><BehaviorTree ID="Main"><Effect/></BehaviorTree></root>)");
  auto status = tree.tickOnce();
  auto start = std::chrono::steady_clock::now();
  tree.haltTree();
  auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
  const int at_halt = effects.load();
  worker.join();
  std::cout << "{\"probe\":\"behaviortree\",\"initial_running\":"
            << (status == BT::NodeStatus::RUNNING ? "true" : "false")
            << ",\"halt_callback_count\":" << halts.load()
            << ",\"effects_at_halt\":" << at_halt
            << ",\"effects_after_halt\":" << effects.load()
            << ",\"halt_return_seconds\":" << elapsed << "}\n";
  return (halts == 1 && at_halt == 0 && effects == 1) ? 0 : 1;
}
