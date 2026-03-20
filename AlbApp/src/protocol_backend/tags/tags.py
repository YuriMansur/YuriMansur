# Dev_192_168_6_6_OPC_Tags.py
# Auto-generated OPC UA tag constants

class Dev_192_168_6_6_OPC_Tags:
    cmdPowerOn = "ns=4;s=|var|Xinje-Cortex-Linux-SM-CNC.Application.MAIN.StandLogicEx.cmdPowerOn"
    cmdPowerOff = "ns=4;s=|var|Xinje-Cortex-Linux-SM-CNC.Application.MAIN.StandLogicEx.cmdPowerOff"
    cmdForwardJogging = "ns=4;s=|var|Xinje-Cortex-Linux-SM-CNC.Application.MAIN.StandLogicEx.cmdForwardJogging"
    cmdBackwardJogging = "ns=4;s=|var|Xinje-Cortex-Linux-SM-CNC.Application.MAIN.StandLogicEx.cmdBackwardJogging"
    cmdChangeControlMode = "ns=4;s=|var|Xinje-Cortex-Linux-SM-CNC.Application.MAIN.StandLogicEx.cmdChangeControlMode"
    cc = "ns=4;s=|var|Xinje-Cortex-Linux-SM-CNC.Application.MAIN.StandLogicEx.cc"
    tenzaSensorDataArr = "ns=4;s=|var|Xinje-Cortex-Linux-SM-CNC.Application.MAIN.StandLogicEx.tenzaSensorDataArr"


# Использование:
#   from tags import Dev_192_168_6_6_OPC_Tags
#   backend.read_node(server_id, Dev_192_168_6_6_OPC_Tags.Temperature)