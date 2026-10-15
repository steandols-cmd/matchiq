// Preload: exponerar ett minimalt, typat API till gränssnittet. Ingen Node-åtkomst i renderer.
import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("matchiq", {
  getBackend: () => ipcRenderer.invoke("matchiq:getBackend"),
  openPath: (p: string) => ipcRenderer.invoke("matchiq:openPath", p),
  showItemInFolder: (p: string) => ipcRenderer.invoke("matchiq:showItemInFolder", p),
  setBackgroundMode: (enabled: boolean) => ipcRenderer.invoke("matchiq:setBackgroundMode", enabled),
  getBackgroundMode: () => ipcRenderer.invoke("matchiq:getBackgroundMode"),
  pickFile: (filters?: { name: string; extensions: string[] }[]) => ipcRenderer.invoke("matchiq:pickFile", filters),
  platform: process.platform,
  version: process.versions.electron,
});
