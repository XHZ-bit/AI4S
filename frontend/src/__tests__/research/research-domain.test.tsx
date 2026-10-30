import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import ResearchDomainInput,{parseResearchDomain,researchDomainValue} from '../../components/research/ResearchDomainInput';
import ProjectSettingsPanel from '../../components/research/ProjectSettingsPanel';
import {DOMAIN_PROFILES} from '../../api/project-types';
import {project} from './fixtures';

const api=vi.hoisted(()=>({updateProject:vi.fn()}));
vi.mock('../../api/projects',()=>({...api,isVersionConflict:()=>false}));
beforeEach(()=>{api.updateProject.mockReset().mockResolvedValue({...project,domain:'custom',custom_domain:'具身智能与臂手协同'})});

test('free text remains a custom research domain while known suggestions retain their profile',()=>{
 expect(parseResearchDomain('  具身智能与臂手协同  ')).toEqual({domain:'custom',custom_domain:'具身智能与臂手协同'});
 expect(parseResearchDomain(DOMAIN_PROFILES.robot_policy_learning.label)).toEqual({domain:'robot_policy_learning',custom_domain:null});
 expect(parseResearchDomain('robot_policy_learning')).toEqual({domain:'robot_policy_learning',custom_domain:null});
 expect(parseResearchDomain('  ')).toEqual({domain:'custom',custom_domain:null});
 expect(researchDomainValue('custom','数字人文')).toBe('数字人文');
 const changed=vi.fn();render(<ResearchDomainInput onChange={changed}/>);
 fireEvent.change(screen.getByRole('combobox',{name:'研究领域'}),{target:{value:'具身智能与臂手协同'}});
 expect(changed.mock.lastCall?.[0]).toBe('具身智能与臂手协同');
});

test('project settings accept a new domain directly and send it in custom_domain',async()=>{
 const saved=vi.fn();render(<ProjectSettingsPanel project={{...project,domain:'custom',custom_domain:'数字人文'}} onSaved={saved}/>);
 const input=await screen.findByDisplayValue('数字人文');
 fireEvent.change(input,{target:{value:'具身智能与臂手协同'}});
 fireEvent.click(screen.getByRole('button',{name:'保存新版本'}));
 await waitFor(()=>expect(api.updateProject).toHaveBeenCalledWith('project-1',expect.objectContaining({expected_version:project.version,domain:'custom',custom_domain:'具身智能与臂手协同'})));
 expect(saved).toHaveBeenCalledTimes(1);
});

test('choosing a recognized domain clears an obsolete custom label on save',async()=>{
 render(<ProjectSettingsPanel project={{...project,domain:'custom',custom_domain:'旧自定义领域'}} onSaved={vi.fn()}/>);
 fireEvent.change(await screen.findByDisplayValue('旧自定义领域'),{target:{value:DOMAIN_PROFILES.image_anomaly_detection.label}});
 fireEvent.click(screen.getByRole('button',{name:'保存新版本'}));
 await waitFor(()=>expect(api.updateProject).toHaveBeenCalledWith('project-1',expect.objectContaining({domain:'image_anomaly_detection',custom_domain:null})));
});
