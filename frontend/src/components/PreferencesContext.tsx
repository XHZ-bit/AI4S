import {createContext,useContext,useEffect,useState,type ReactNode} from "react";
import {defaultPreferences,getPreferences,type Preferences} from "../api/preferences";
const Context=createContext({preferences:defaultPreferences,loading:false,error:"",adopt:(_value:Preferences)=>{}});
export const usePreferences=()=>useContext(Context);
export default function PreferencesProvider({children}:{children:ReactNode}){
 const [preferences,setPreferences]=useState(defaultPreferences),[loading,setLoading]=useState(true),[error,setError]=useState("");
 useEffect(()=>{const controller=new AbortController();getPreferences(controller.signal).then(setPreferences).catch(e=>{if(!controller.signal.aborted)setError(String(e));}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();},[]);
 return <Context.Provider value={{preferences,loading,error,adopt:setPreferences}}>{children}</Context.Provider>;
}
