export interface LearningStep {question:string;explanation:string;example?:string;check?:string}
export interface LearningQuiz {question:string;options:string[]}
export interface Exercise {id:string;kind:string;title:string;prompt:string;starter:string;hint:string;tests:string;solution:string;test_count:number}
export interface Lesson {id:string;title:string;summary:string;minutes:number;connection:string;prerequisites:string[];steps:LearningStep[];terms:{term:string;definition:string}[];quiz:LearningQuiz[];exercise:Exercise|null;visual:string|null}
export interface TutorResult{id:string;model:string;timings?:{model_seconds?:number;total_seconds?:number};source?:{paper_uid?:string;passage_id?:string;title?:string;passage?:{page?:number}}|null;plan:{exercise?:Exercise|null;title:string;goal:string;prerequisites:string[];steps:LearningStep[];terms:{term:string;definition:string}[];quiz:LearningQuiz[]}}
