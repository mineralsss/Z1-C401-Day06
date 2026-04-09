import os
from dotenv import load_dotenv

load_dotenv()  # phải load trước khi dùng os.getenv

from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from tools import get_nearest_branch, get_suitable_availibility_doctor, get_today_date, get_all_specialties, get_doctor_schedule, confirm_appointment_summary, book_appointment, get_doctor_profile
from dotenv import load_dotenv

load_dotenv()

# 1. Đọc System Prompt
with open("system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

# 2. Khai báo State
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

# 3. Khởi tạo LLM và Tools
tools_list = [get_doctor_schedule, confirm_appointment_summary, book_appointment,get_doctor_profile, get_nearest_branch, get_suitable_availibility_doctor, get_today_date, get_all_specialties]
llm = ChatOpenAI(model="gpt-4o-mini")
llm_with_tools = llm.bind_tools(tools_list)

# 4. Agent Node
def agent_node(state: AgentState):
    messages = state["messages"]
    if not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    response = llm_with_tools.invoke(messages)
    
    # === LOGGING ===
    if response.tool_calls:
        for tc in response.tool_calls:
            print(f"  → Gọi tool: {tc['name']}({tc['args']})")
    else:
        print("  → Trả lời trực tiếp")
        
    return {"messages": [response]}

# 5. Xây dựng Graph
builder = StateGraph(AgentState)
builder.add_node("agent", agent_node)

tool_node = ToolNode(tools_list)
builder.add_node("tools", tool_node)

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

graph = builder.compile()

# 6. Chat loop
if __name__ == "__main__":
    print("=" * 60)
    print("Trợ lý ảo tư vấn bác sĩ - Vinmec")
    print(" Gõ 'quit' để thoát")
    print("=" * 60)
    conversation_messages = []
    
    while True:
        user_input = input("\nBạn: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
            
        print("\nVinmecAI đang suy nghĩ...")
        result = graph.invoke(
            {"messages": conversation_messages + [("human", user_input)]}
        )
        conversation_messages = result["messages"]
        final = result["messages"][-1]
        print(f"\nVinmecAI: {final.content}")