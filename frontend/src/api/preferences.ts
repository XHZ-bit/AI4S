import { authenticatedFetch } from "./session";
import { apiGet } from "./client";
export type Feature = "foundations"|"glossary"|"quizzes"|"coding"|"visuals"|"paper_guidance"|"roadmap"|"graph";
export interface Preferences {
 profile:{display_name:string;bio:string;institution:string;interests:string;level:"beginner"|"reader"|"researcher";weekly_hours:number};
 features:Record<Feature,boolean>;
 provider:{enabled:boolean;base_url:string;model:string;has_key?:boolean;api_key?:string;clear_key?:boolean};
 version:number;default_model?:string;avatar_url?:string|null;
}
export const featureLabels:Record<Feature,[string,string]>={
 foundations:["基础知识补课","按需补充概率论、线性代数等前置知识"],
 glossary:["术语解释","解释论文里的专业词汇与变量含义"],
 quizzes:["理解检查与小测","作答后显示反馈，并保留练习记录"],
 coding:["交互式代码训练","填空、调试、函数编写和模块化练习"],
 visuals:["可视化演示","通过滑块和图形观察数学概念的变化"],
 paper_guidance:["逐步辅导与论文解读","主动提问时调用你选择的模型"],
 roadmap:["学习与科研路线","显示学习路线和完整案例入口"],
 graph:["知识图谱","查看概念、方法和论文之间的关系"]
};
export const presets:Record<string,Record<Feature,boolean>>={
 beginner:{foundations:true,glossary:true,quizzes:true,coding:true,visuals:true,paper_guidance:true,roadmap:true,graph:true},
 reader:{foundations:false,glossary:true,quizzes:true,coding:false,visuals:true,paper_guidance:true,roadmap:true,graph:true},
 researcher:{foundations:false,glossary:false,quizzes:false,coding:false,visuals:false,paper_guidance:false,roadmap:true,graph:true}
};
export const defaultPreferences:Preferences={profile:{display_name:"",bio:"",institution:"",interests:"",level:"beginner",weekly_hours:5},features:presets.beginner,provider:{enabled:false,base_url:"",model:""},version:0};
export const getPreferences=(signal?:AbortSignal)=>apiGet<Preferences>("/api/preferences",undefined,signal);
export async function savePreferences(value:Preferences){
 const {avatar_url,default_model,...body}=value;const {has_key,...provider}=body.provider;
 const response=await authenticatedFetch("/api/preferences",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({...body,provider})});
 if(!response.ok){const error=await response.json();throw new Error(typeof error.detail==="string"?error.detail:"设置未保存，请检查填写内容");}return response.json() as Promise<Preferences>;
}
