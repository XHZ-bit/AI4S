import {expect,test} from 'vitest';
import {applyNodePositions,dragPosition,resolveNodeDrop,restoreNodeLayouts} from '../components/knowledge/GraphInteraction';
import {NODE_WIDTH,NODE_HEIGHT,type GraphLayout} from '../components/knowledge/KnowledgeGraphLayout';

const layout=():GraphLayout=>({points:new Map([['a',{x:40,y:50,depth:0}],['b',{x:400,y:50,depth:1}]]),lanes:[],width:760,height:410,hub:{x:40,y:50}});
test('drag coordinates account for zoom and stay within the reachable canvas',()=>{
 expect(dragPosition({x:100,y:100},80,40,.5)).toEqual({x:260,y:180});
 expect(dragPosition({x:100,y:100},-900,-900,2)).toEqual({x:16,y:16});
});
test('restoring user layouts rejects invalid coordinates and other project scopes',()=>{
 expect(restoreNodeLayouts({'p/all':{a:{x:40,y:50},b:{x:'20',y:20},c:{x:Infinity,y:0}},'other/all':{a:{x:10,y:20}},'p/source':{a:{x:400,y:200}}},'p')).toEqual({'p/all':{a:{x:40,y:50}},'p/source':{a:{x:400,y:200}}});
});
test('saved positions follow node IDs and extend the canvas without changing automatic coordinates',()=>{
 const base=layout(),moved=applyNodePositions(base,{a:{x:1000,y:700},missing:{x:9000,y:9000}});
 expect(moved.points.get('a')).toEqual({x:1000,y:700,depth:0});
 expect(base.points.get('a')).toEqual({x:40,y:50,depth:0});
 expect(moved.points.get('b')).toEqual(base.points.get('b'));
 expect(moved.width).toBe(1000+NODE_WIDTH+36);
 expect(moved.height).toBe(700+NODE_HEIGHT+36);
});
test('dropping on another node chooses a nearby unobscured position',()=>{
 const base=layout(),point=resolveNodeDrop(base,'a',{x:400,y:50}),b=base.points.get('b')!;
 expect(point).not.toEqual({x:400,y:50});
 expect(point.x+NODE_WIDTH+20<=b.x||b.x+NODE_WIDTH+20<=point.x||point.y+NODE_HEIGHT+20<=b.y||b.y+NODE_HEIGHT+20<=point.y).toBe(true);
 expect(resolveNodeDrop(base,'a',{x:40,y:220})).toEqual({x:40,y:220});
});
